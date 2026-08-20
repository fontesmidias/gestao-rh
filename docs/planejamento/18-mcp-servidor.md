# Servidor MCP do Portal — em construção

> Status: **começado em 2026-08-20, incompleto**. Este documento diz onde parei
> e o que falta, para retomar sem refazer o caminho.

## O que decidiu o desenho

Três fatos, nesta ordem:

1. O uso é dos **colaboradores do RH** (2 a 5 pessoas, diariamente), não da
   Claude de uma pessoa só — daí o papel `assistente_rh` da v3.13.
2. O Claude **na web** só conecta MCP remoto por **OAuth**; não aceita token em
   header (issue #112, fechado como *not planned*). Isso levou ao desenho do
   `17-mcp-oauth.md`.
3. **Todos já têm o Claude Desktop** (Bruno, 20/08/2026) — e o Desktop roda o
   servidor por `command` + `args`, com segredo em variável de ambiente.

O (3) tornou o (2) desnecessário: **o token `mcp_…` que já existe funciona**, sem
provedor OAuth nenhum. O `17-mcp-oauth.md` ficou arquivado com o motivo, porque
o obstáculo volta se um dia alguém precisar usar pelo navegador.

## Onde o servidor mora, e por quê

`mcp/` — pacote **separado do backend**, com `pyproject.toml` próprio. Não é
organização: o servidor roda no **computador de cada pessoa**, e o backend roda
no VPS. Misturá-los faria a imagem da API carregar o SDK do MCP sem precisar, e
o doc 13 § 4 já rejeitou pôr as rotas do MCP dentro da API do painel — a
superfície da IA não se funde com a do humano.

## O que já existe

- **`mcp/pyproject.toml`** — dependências (`mcp[cli]`, `httpx`) e o comando
  `portal-rh-mcp`.
- **`mcp/portal_rh_mcp/portal.py`** — o cliente HTTP. A parte que importa é o
  tratamento de erro: 401, 403, 404, 429 e timeout têm mensagens DIFERENTES,
  porque cada um pede uma ação diferente (v2.93) — e num assistente isso pesa
  mais, já que o modelo vai LER a mensagem e repeti-la para a pessoa.
  O token vem do AMBIENTE, nunca de argumento: o modelo não o vê e não tem como
  vazá-lo numa resposta.

## O que falta

1. **`servidor.py`** — registrar as ferramentas com o SDK e o `main()` do
   `stdio`.
2. **As ferramentas de leitura** (doc 13 § 6): `buscar_candidato`,
   `pendencias_admissao`, `status_documentos`, `diagnostico_dossie`,
   `listar_admissoes`, `pendencias_tirvu`. ⚠️ `api/diagnostico.py` **já responde
   4 delas** — as ferramentas são cascas finas, não código novo.
3. **As de escrita**, uma a uma: `cadastrar_talento` (casca sobre
   `POST /rh/talentos`, que já deduplica), e depois o que a decisão de 19/08
   liberou — convidar, aprovar documento, marcar entrevista.
4. **O guia de instalação** para as 2 a 5 pessoas: como criar a própria
   credencial na tela e o que colar no `claude_desktop_config.json`.
5. **Mascaramento na saída** (doc 13 § 5.5) e o `anti_prompt_injection` em todo
   texto que volte ao modelo (§ 5.4) — currículo e anotação de CRM são entrada
   hostil.

## Armadilhas já conhecidas para esta parte

- **Não reimplementar dedup** (doc 13 § 3): `POST /rh/talentos` já recusa
  duplicata nomeando quem é. Duas portas discordando sobre a mesma pessoa é o
  defeito que a v2.73 evitou.
- **Não processar 14 mil currículos de uma vez** (§ 7): lote de 50, medir,
  ajustar. Velocidade em fila errada multiplica erro.
- **Toda chamada vai à auditoria** marcada como automação — o `requer_rh` já faz
  isso com `automacao:<e-mail de quem age>`, e é o que responde "quem mandou?".
