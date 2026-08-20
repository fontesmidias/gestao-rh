# Servidor MCP do Portal — onde está e o que falta

> Status: **este é o servidor STDIO** — o caminho manual, que continua válido
> para quem quiser rodar no próprio computador.
>
> ⚠️ **O caminho principal passou a ser o MCP remoto com OAuth** (v3.15): a
> pessoa adiciona o endereço do portal como conector e faz login, sem instalar
> nada e sem credencial para colar. Veja **`17-mcp-oauth.md`** e o guia
> `mcp/CONECTAR.md`.
>
> Este documento segue valendo para o servidor stdio: as 5 ferramentas são as
> MESMAS, e as descrições delas são comparadas por teste entre os dois — se
> divergirem, o remoto e o local respondem diferente à mesma pergunta.
>
> Para **o desenho e o que não se expõe**, veja `13-mcp-do-portal.md` — ele é o
> contrato, e um teste o cobra.

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

## O que existe (v3.14)

| Arquivo | O que é |
|---|---|
| `pyproject.toml` | Dependências e o comando `portal-rh-mcp`. O SDK está cravado em `>=2.0,<3` — ver a armadilha abaixo |
| `portal_rh_mcp/portal.py` | O cliente HTTP. 401, 403, 404, 429 e timeout têm mensagens **diferentes**, porque cada um pede uma ação diferente (v2.93). O token vem do AMBIENTE, nunca de argumento |
| `portal_rh_mcp/saida.py` | Máscara de CPF e neutralização de prompt injection na saída |
| `portal_rh_mcp/servidor.py` | As 6 ferramentas e o `main()` do `stdio` |
| `tests/test_mcp_ferramentas.py` | Sobe o servidor e lista as ferramentas. **Fora do CI** (precisa do SDK) |
| `backend/tests/test_mcp_saida.py` | Compara a defesa copiada com a do backend. **No CI** |
| `backend/tests/test_mcp_permissoes.py` | Cada rota chamada cabe no papel `assistente_rh`. **No CI** |
| `README.md` | O guia de instalação das 2 a 5 pessoas |

As ferramentas: `buscar_candidato`, `diagnostico_candidato`, `listar_admissoes`,
`pendencias_tirvu` e `cadastrar_talento`. Todas são **cascas finas** sobre rotas
existentes — `api/diagnostico.py` já respondia quatro perguntas do § 6 numa rota
só.

⚠️ **`erros_recentes` foi tirada, e a ausência é decisão.** A rota que a serviria
exige `sistema:telemetria`, que nenhum dos dois papéis tem — ela responderia 403
para todo mundo, sempre. Conceder a permissão daria de quebra 12 rotas de
telemetria ao assistente, o oposto do § 5.2. Não a ressuscite sem resolver isso;
o `test_mcp_permissoes.py` reprova.

## O que falta

1. **Rodar com gente de verdade.** As 2 a 5 pessoas instalarem e usarem por
   alguns dias. Só o uso dirá se as descrições das ferramentas fazem o modelo
   escolher a certa — e é isso que o § 8 do doc 13 chama de documentação
   funcional.
2. **O lote-piloto de 50 currículos** (§ 7 do doc 13), medido e relatado. ⚠️ O
   intervalo de datas é **parâmetro**, nunca constante, e vai para a auditoria:
   sem ele não se sabe depois o que já foi varrido. Rodada sem intervalo
   informado **recusa**.
3. **As ferramentas de escrita que a decisão de 19/08 liberou** — convidar
   candidato, aprovar documento, marcar entrevista. O papel `assistente_rh` já
   tem as permissões; falta a casca. Uma a uma, não as três de uma vez.
4. **Subir o currículo pelo MCP.** Hoje `cadastrar_talento` cria o registro e o
   arquivo sobe pela tela. A rota existe (`POST /rh/talentos/{id}/curriculo`);
   falta decidir como o arquivo chega até ela a partir do Desktop.

## Armadilhas já conhecidas para esta parte

- **O SDK renomeou a classe principal entre majors.** `FastMCP` (1.x) virou
  `MCPServer` (2.x), e o código escrito contra a 1.x **não sobe** com a 2.0
  instalada. Só apareceu porque o teste sobe o servidor e LISTA as ferramentas;
  `import portal_rh_mcp` teria ficado verde com tudo quebrado (v3.00.6). Por
  isso a faixa está fechada no major — faixa aberta já quebrou este projeto
  sozinha, com o sintoma culpando a credencial (v3.00.4).
- **A defesa de injection está COPIADA**, porque o pacote roda no desktop e não
  importa o backend. `test_mcp_saida.py` compara os dois arquivos e reprova a
  divergência; ao mexer num, mexa no outro.
- **Neutralizar não pode tornar o texto ilegível.** Separar todas as letras do
  trecho suspeito neutraliza e devolve algo que ninguém lê nem copia — e quem
  opera precisa ver o que a pessoa escreveu. Um separador basta.
- **Nada em `stdout` além do protocolo.** Um `print` de depuração corrompe a
  conversa com o Desktop, e o sintoma aparece como "o servidor não conecta".
  Depure por `stderr`.
- **Não reimplementar dedup** (doc 13 § 3): `POST /rh/talentos` já recusa
  duplicata nomeando quem é.
- **Não processar 14 mil de uma vez** (§ 7): lote de 50, medir, ajustar.
  Velocidade em fila errada multiplica erro.
- **Toda chamada vai à auditoria** marcada como automação — o `requer_rh` já faz
  isso com `automacao:<e-mail de quem age>`, e é o que responde "quem mandou?".
  Por isso **cada pessoa tem o seu token**: um compartilhado devolveria a
  pergunta ao vazio.
