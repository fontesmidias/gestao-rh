# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/) · versionamento semântico.

Rollback: toda migration tem `downgrade()` escrito para não destruir dados —
`alembic downgrade -1` volta uma revisão; o código volta apontando a stack para a
tag anterior da imagem no GHCR. Faça `pg_dump` antes de qualquer downgrade.

> **Sobre "legado"**: valores de enum e campos que deixaram de ser usados **não
> são removidos** — o Postgres não apaga valor de enum sem recriar o tipo, e
> apagar coluna destruiria histórico. Eles ficam órfãos (não se escreve mais),
> com o motivo registrado abaixo e no `CLAUDE.md`. NÃO usar em código novo.

## [2.26.0] — 2026-07-30 — A tela de Telemetria estava fora do padrão visual

Feedback do Bruno: *"achei tão feia essa página, por que não seguiu o padrão de
layout? de cards, espaçamentos, alinhamentos?"*. Estava certo, e a causa não era
gosto.

### Corrigido
- **Onze classes de CSS inventadas** (`rh-secao`, `rh-bloco`, `rh-acoes`,
  `rh-form-inline`, `campo-check`…) que **não existiam** no `styles.css`. O JSX
  parecia correto e o build passava — CSS não reclama de seletor inexistente —,
  mas a tela saía crua: sem card, sem borda, sem espaçamento.
- As três telas (`TelemetriaRH`, `AlertasTelemetria`, `TelemetriaPessoa`)
  reescritas com as primitivas reais de `08-sistema-de-design.md`: `.rh-card`,
  `.rh-grid-2`, `.rh-topo`, `.rh-metricas`, `.rh-tabela`, `.campo`/`.rotulo`.
- **Cores em hex cru** (`'#c33'`, `'#c80'`) trocadas pelos tokens semânticos
  `var(--perigo)` / `var(--atencao)`, que invertem no tema escuro.
- Duas classes genuinamente novas entraram no `styles.css` com tokens, em vez de
  serem inventadas no JSX: `.bloco-codigo` (JSON de detalhe, rola na horizontal
  em vez de esticar o card) e `.campo-sem-margem`.

### Verificação
Auditoria automática dos três arquivos: nenhuma classe sem CSS, nenhum token
inexistente, nenhum hex cru. Conferido visualmente nos temas **claro e escuro**.

### Lição registrada no CLAUDE.md
Classe que não existe não estiliza nada, e o build não avisa. Antes de commitar
tela nova: `grep` de cada classe usada no `styles.css` — e ler o sistema de
design **antes** de escrever, não depois do feedback.

---

## [2.25.0] — 2026-07-30 — Alertas: o sistema avisa em vez de esperar a pergunta

A telemetria da v2.24 grava tudo certo, mas é **passiva** — alguém precisa abrir
a aba. No incidente de 29/07 isso não bastaria: o erro estaria gravado às 11h01
e a descoberta continuaria dependendo de o candidato ligar.

### Adicionado
- **Quatro tipos de alerta**, todos com regras **editáveis na tela** (nada de
  limiar chumbado no código — quem convive com os números é quem deve ajustá-los):
  - **Erro novo** — uma mensagem que nunca tinha aparecido. O caso de 29/07:
    teria avisado às 11h05.
  - **Volume de erros** — um erro conhecido que disparou; assinatura clássica de
    deploy ruim.
  - **Pico de travamentos** — muita gente travando no mesmo ponto. Indica que
    algo quebrou, não que as pessoas estão desatentas.
  - **Lentidão** — página acima do tempo aceitável **para a maioria** (mediana).
- **Entrega pela matriz de avisos internos** (evento `telemetria_alerta`), com
  texto editável no catálogo de e-mails — a mesma mecânica dos outros 40 avisos,
  nenhum caminho paralelo.
- **Worker `alertas` a cada 15 minutos**, serviço próprio no compose e no stack
  do Portainer. Não foi embutido no `expurgo` (24h): ali o alerta chegaria um
  dia depois e não serviria para nada.
- **"O que dispararia agora?"** — simulação que **não envia e não gasta o
  silêncio**. Testar não pode impedir o alerta real de chegar depois.
- **Histórico de alertas enviados**, com destaque em vermelho quando o alerta
  saiu para **ninguém** (destinatário não cadastrado): sem isso, caixa silenciosa
  seria ambígua — "não houve problema" e "quebrou" pareceriam iguais.
- Quatro regras já ativas na migration: o recurso nasce vigiando, em vez de
  esperar alguém configurar o que ainda não doeu.

### Corrigido
- **`/c/assinatura` era mascarado como se fosse token** (`/c/assina***`), e o
  mesmo erro aparecia **duas vezes** no alerta — uma por grafia, como se fossem
  problemas diferentes. Agrupar errado infla a contagem e esconde o padrão.
  `_parece_token` agora exige tamanho **e** caixa mista: nome de etapa nunca tem
  as duas coisas.
- **O teste do catálogo de e-mails travava o NÚMERO de avisos** (`== 8`). Cada
  aviso legítimo quebraria o teste sem apontar defeito, e a tentação seria só
  incrementar a constante — um teste que não protege nada. Agora o vínculo
  aviso↔evento é derivado do próprio catálogo.

### Corrigido depois, ao conferir a stack de produção
- **O botão "Ver na telemetria" do e-mail saía vazio**: o template declarava o
  botão, mas o `alertas.py` nunca passava a variável `link`. O worker roda no
  cron, sem `request`, então não há como derivar a URL da requisição — é o
  único ponto do sistema em que `BASE_URL` é mesmo obrigatório. Adicionado ao
  serviço `alertas` nos dois compose. Um aviso que não leva a lugar nenhum
  obriga o RH a caçar a tela na mão.

### Verificação
`tests/test_alertas.py` (7 blocos) cobre dedup, silêncio por problema,
agrupamento, limiar, mediana, filtro por origem, isolamento entre regras e
histórico. Validado por **mutação** — e a mutação expôs um teste fraco:
desativar a checagem de "já visto" passava. Faltava o caso de que **"novo" é
para sempre**, não pela janela de silêncio; sem ele, um erro conhecido voltaria a
ser anunciado como novidade de hora em hora. Caso adicionado, mutante agora
falha. Ciclo real conferido na stack: 4 erros simulados → alerta disparado →
e-mail entregue → 2ª verificação silenciosa.

---

## [2.24.0] — 2026-07-30 — Telemetria de uso: o que acontece no aparelho das pessoas

Resposta direta ao incidente das v2.22/v2.23. Dois candidatos travaram e o erro
morreu no navegador deles: o servidor registrou **200 em tudo**, porque do lado
dele deu certo — o `TypeError` aconteceu no React, depois da resposta. Não havia
o que procurar em log nenhum.

### Adicionado
- **`EventoTelemetria`** (migration `c9d0e1f2a3b4`) com quatro famílias:
  `erro` (exceção de JS com página, stack e versão do bundle), `friccao` (onde a
  pessoa trava), `jornada` (por onde passou, quanto tempo) e `desempenho`
  (quanto demorou no celular dela, não no servidor).
- **Telemetria individualizada na ficha da pessoa** — candidato, colaborador e
  Banco de Talentos. Responde "não consigo enviar meus documentos" com fato, e
  não com suposição. Segue a pessoa de talento → candidato, como o mini-CRM.
- **Aba Configurações → 📈 Telemetria**, organizada pelas três perguntas que
  importam, nessa ordem: *está quebrando?* (erros **agrupados** por mensagem —
  300 ocorrências do mesmo erro são UM problema, e a lista crua esconderia o
  padrão atrás do volume), *onde as pessoas travam?* e *o que está lento?*
- **Páginas lentas por MEDIANA, não média**: uma chamada de 40s distorceria a
  média e faria parecer que tudo está lento. A mediana mostra o que a maioria
  vive.
- **Retenção configurável** (padrão **1 ano**, para permitir comparação
  sazonal) com expurgo diário automático, e **expurgo por intervalo de datas**
  para limpar o que testes poluíram — registrado na auditoria.

### O que a telemetria NÃO guarda, por decisão de projeto
- **Nada do que a pessoa digita** — só o nome da etapa e o que aconteceu com ela.
- **IP truncado** (`191.180.x.x`): distingue "a operadora está com problema" de
  "o sistema está com problema" sem localizar ninguém.
- **Token do link mágico mascarado**: `/c/{token}` é credencial de acesso, e
  telemetria é feita para ser lida e exportada. Gravá-lo criaria uma planilha de
  chaves de acesso.

### Não é a Auditoria
`EventoAuditoria` responde "quem fez o quê" e é prova de ato — append-only,
nunca expurgada. A telemetria responde "como foi usar" e é descartável por
desenho. Misturar as duas transformaria dado de produto em prova jurídica, e
prova jurídica em lixo que se apaga.

### Verificação
`tests/test_telemetria.py` (8 blocos) cobre mascaramento, minimização de IP,
teto de volume (a rota é pública), agrupamento do resumo, os dois modos de
expurgo e a telemetria por pessoa.

**O teste encontrou um bug real antes do deploy**: as FKs de `candidato`/
`talento` não resolviam sem o import dos modelos, e **toda** gravação falhava —
em silêncio, porque `registrar_eventos` engole exceção por desenho. É a
armadilha da v2.02 ("catch vazio não pode engolir erro de infra") do lado do
servidor. Validado por **mutação**: removido o mascaramento do caminho de
gravação, o teste falha; restaurado, passa.

---

## [2.23.0] — 2026-07-29 — A segunda causa da tela branca: `fichas.some()` sobre `null`

A v2.22 corrigiu o nginx e a tela **continuou quebrando** — agora com a
mensagem do ErrorBoundary em vez do branco, o que revelou o erro que estava
escondido por baixo: `TypeError: Cannot read properties of null (reading 'some')`.

### Corrigido
- **`Assinatura.jsx` usava `fichas.some(...)` no corpo do componente**, mas
  `fichas` nasce `null` e só é preenchido pelo `useEffect`. O guard
  `if (!fichas) return` existia — na linha 54, enquanto o `some` estava na 26.
  O cálculo roda no **primeiro render**, antes de qualquer dado chegar:
  `null.some()` lançava e apagava a tela inteira do candidato.
- **Introduzido na v2.05** (28/07, 20:40), o que confirma a suspeita original de
  que "foi algo das atualizações de ontem para hoje". Atingia exatamente quem
  estava na etapa de **assinatura** — os dois candidatos travados.
- O sintoma engana: parece problema de rede ou de link, porque só acontece na
  janela em que a API ainda não respondeu.

### Verificação
Reproduzido com navegador real contra a stack (`pageerror` capturado, nenhuma
requisição falhando — bug de código puro). Teste novo segura a resposta da API
por 1,5s para renderizar no estado nulo; validado por **mutação** (bug reposto →
o ErrorBoundary aparece e o teste falha; restaurado → 6/6). Varredura no projeto
por `useState(null)` usado antes do guard: nenhum outro caso no caminho do
candidato.

### Lição registrada no CLAUDE.md
Estado que nasce `null` não pode ser usado no corpo do componente — o guard vem
antes do primeiro uso, não junto do `return`.

---

## [2.22.0] — 2026-07-29 — Tela em branco no candidato: o deploy apagava o script que a aba pedia

Incidente de produção. Dois candidatos travados no meio do envio da
documentação, com a **tela em branco** ao reabrir o link — e nenhuma linha de
erro em log nenhum.

### Corrigido
- **`try_files $uri /index.html` valia também para `/assets/*.js`.** Cada build
  gera assets com hash novo (`index-C1OewSkj.js`) e apaga os anteriores. O
  candidato deixa a página aberta no celular — ele sai para fotografar o
  documento e volta, que é o uso normal. Se um deploy acontece nesse meio, a aba
  pede o arquivo antigo e o nginx respondia **HTTP 200 com o HTML do index no
  lugar do JavaScript**; o navegador tentava executar `<!doctype html>` como
  script, e o React não montava. Agora `/assets/` usa `try_files $uri =404`.
- **Por que não havia o que procurar no log**: do ponto de vista do servidor foi
  um 200 bem-sucedido. O defeito era invisível para quem olhava só o servidor.
- **Explica os dois casos, inclusive o link criado no mesmo dia**: não depende de
  quando o link nasceu, e sim de a aba estar aberta durante um deploy.
- **`STATUS[s.status]` sem guarda no checklist** (`Checklist.jsx`): status
  desconhecido lançaria `TypeError` e mataria a tela igual. Não foi o gatilho
  deste incidente, mas era a mesma bomba armada.

### Adicionado
- **`ErroFatal.jsx` — o primeiro ErrorBoundary do projeto.** Não havia nenhum:
  qualquer exceção de render apagava a aplicação inteira, sem uma palavra na
  tela. Tela branca é o pior desfecho para quem está do outro lado, porque não
  diz se o problema é a internet, o link, o celular ou o sistema — a pessoa
  conclui que "não funciona" e desiste.
- **Recuperação automática de aba antiga** (`main.jsx`): falha ao carregar
  módulo = versão velha, então recarrega **uma** vez buscando o `index.html`
  novo. A trava em `sessionStorage` é obrigatória — sem ela, uma falha permanente
  viraria recarregamento infinito, que é pior que a tela branca.
- **`/api/health` mostra `migracoes.em_dia`**: se o `docker-entrypoint` falhar ao
  rodar `alembic upgrade head`, a API sobe com o schema velho e o defeito só
  aparece na cara do candidato. A revisão é **lida** do diretório de migrations —
  o `VERSAO_DEPLOY` estava congelado em `v1.50` havia vinte versões, mentindo
  com confiança.
- **Cache `immutable` nos assets**: o hash está no nome, então cachear para
  sempre é seguro e economiza banda no celular do candidato.

### Verificação
`tests/e2e/deploy-tela-branca.spec.js` roda contra o nginx real. Validado por
**mutação**: removido o bloco `/assets/`, o asset antigo voltou a responder 200
com `text/html` e o teste falhou onde devia; restaurado, 5/5 passam. Confirmado
que `/c/{token}` continua servindo o SPA — consertar o asset não podia quebrar a
navegação, que é por onde o candidato entra.

### Não era migration
Medido, não suposto: com o banco atrasado o painel do RH e o creche quebram
(`teste_vinculado` e `link_expira_em` não existem), mas as rotas do candidato
respondem 200. O `docker-entrypoint.sh` roda `alembic upgrade head`
corretamente.

---

## [2.21.0] — 2026-07-29 — Teste já respondido aproveitado no candidato

### Adicionado
- **`TesteVinculado`**: o RH aproveita para o candidato um DISC/situacional ou
  prova que a pessoa já respondeu antes de virar candidata. **Aponta, não copia**
  — o resultado é lido na origem; copiar criaria duas versões do mesmo dado e
  nenhuma confiável.
- **A identidade é registrada como o que é**: `automatico=True` quando veio do
  Banco de Talentos (o link tinha `talento_id`); `automatico=False` quando o RH
  escolheu da lista, com autor snapshot. Importa porque o link avulso de testagem
  é **anônimo** e teste decide contratação — vincular o resultado de um homônimo
  é decidir a vida de alguém com dado de outro. Por isso a lista de escolha mostra
  nome, data, qual teste e por qual link.
- **Só o RH vê**: não entra no wizard nem no dossiê, que circula.
- **Destinatários na tela dos textos de e-mail**: quem recebe cada aviso interno,
  editável junto do texto. Grava na **mesma** matriz de Avisos internos — uma
  fonte exposta em dois lugares, não duas verdades.

## [2.20.0] — 2026-07-29 — Avisos internos entram no catálogo

### Adicionado
- **`avisar_modelo(db, evento, chave_template, contexto)`**: os 8 avisos que vão
  à equipe passaram a ter assunto e corpo editáveis. O motivo não é cosmético —
  **quem recebe nem sempre conhece o sistema**: o Gabriel e o Vitor recebem o de
  uniforme, o líder de brigada recebe o de certificação vencendo.
- Catálogo vai a 40 templates. Template ausente degrada para 0 envios + log:
  aviso interno que falha nunca pode derrubar a ação do candidato que o disparou.

### Corrigido
- **O aviso "Dossiê pronto" lia `email_avisos_internos` direto, fora da matriz.**
  Desligar o evento no painel não o desligava, e cadastrar destinatário não
  funcionava — o RH configurava a matriz achando que ela governava tudo.

## [2.19.0] — 2026-07-29 — Catálogo dos documentos do sistema

### Adicionado
- Os 11 documentos da admissão numa tela só, com **amostra em PDF de verdade**
  (mesmo gerador, candidato fictício que nunca vai ao banco), download e "criar
  modelo a partir deste" nos de texto corrido.
- **Nenhum gerador foi substituído, e não devem ser**: o hash do ato de
  assinatura é calculado sobre o PDF gerado — trocar por template faria os
  manifestos já emitidos apontarem para um hash que não se reproduz.

### Corrigido
- A primeira versão trazia a lista de direitos do "Informações ao Trabalhador"
  escrita à mão, e **perdera 6% do VT, 8% do FGTS e o 5º dia útil** — texto
  plausível e errado num documento de contrato com órgão público. Virou
  `fichas.DIREITOS_TRABALHADOR` (fonte única) e o teste ganhou **âncoras**;
  "corpo não vazio + tem `{{`" deixava texto inventado passar.

## [2.18.0] — 2026-07-29 — A mensagem parou de culpar a coisa errada

### Corrigido
- `Assinatura.jsx` dizia **"verifique sua conexão"** para erro de cota — pior que
  inútil: a conexão está ótima e a frase convida a tentar de novo na hora,
  reabastecendo a cota.
- `AssinarExterno.jsx` tinha `catch {}` **mudo** ao pedir código: a falha não
  aparecia em lugar nenhum.
- "Código incorreto" passou a dizer o que resolve: **use o do e-mail mais
  recente** — só o último vale.

### Medido
Na assinatura e no teste o código é sobrescrito no mesmo registro, então **o
último enviado continua valendo depois do 429** (`test_codigo_cota.py`). Sem essa
garantia, a orientação na tela seria mentira.

## [2.17.0] — 2026-07-29 — O link do e-mail entra direto

Feedback de campo: *"foi eu mesmo quem copiou e colou o código. Impossível ter
erro."* Estava certo — o código era válido.

### Corrigido
- A cota é 5 pedidos por 15 min. Estourada, o e-mail **não saía**, mas o front
  **avançava de etapa assim mesmo** — sucesso mentiroso, o mesmo defeito da
  v2.02 pela terceira vez. A pessoa colava o código do e-mail anterior.
- 429 ganhou frase própria; botão "🔄 Reenviar o código" na própria tela.
- `confirmar` deixou de exigir `confirmado_em IS NULL`: quem entrava pelo link e
  ainda digitava o código levava "código inválido" com o código certo na mão.

### Adicionado
- **Link do e-mail entra direto** (creche e portal `/meu`): código e link chegam
  na mesma caixa, logo provam o mesmo fator — exigir os dois era atrito
  duplicado, não segurança em camadas. Uso único, 15 min. Migration
  `a8b9c0d1e2f3`; nulo = acesso antigo, que segue exigindo código.

## [2.16.0] — 2026-07-28 — "Enviar teste para mim" nos textos de e-mail

### Adicionado
- Manda o texto **em edição** para a caixa de quem está editando — ver como
  chega antes de valer para o candidato.

## [2.15.0] — 2026-07-28 — Currículo e anotações na linha do dash

### Adicionado
- O dash de Talentos mostrava "🗒️ Anotações" em todo mundo e o RH só descobria
  que não havia nada depois de abrir o modal. Agora vêm a contagem e a última
  anotação, carregadas **em lote**.

### Corrigido
- **O teste de N+1 escrito para isso expôs um N+1 antigo**: `_resumo_teste_talento`
  fazia até 3 consultas por talento, com o comentário "1 consulta, sem N+1" logo
  acima. A listagem caiu de **43 consultas para 39 talentos → 5**, constante.
- Armadilha registrada: medir N+1 com limite absoluto mede o tamanho do banco —
  compare duas listagens de tamanhos diferentes.

## [2.14.0] — 2026-07-28 — Arquivar talento registra motivo, autor e data

### Adicionado
- Arquivar **escreve no mini-CRM** em vez de ganhar campo próprio: a `Anotacao`
  já tinha texto, anexo, autor snapshot e data. Desfazer é mudar o status de
  volta; o registro permanece porque a anotação é append-only.
- O lote **presta contas de quem não foi** — antes tinha `.catch(() => {})` e
  dizia que arquivou tudo.

### Corrigido
- `test_jornadas_confirmar_lote` só passava em banco limpo (`descricao` é
  `unique=True`). Teste que grava em tabela com campo único precisa gerar o valor
  por execução.

## [2.13.0] — 2026-07-28 — Confirmar em lote as jornadas que o parser leu por completo

### Adicionado
- Só as **completas** entram no lote; as demais continuam uma a uma.

## [2.12.0] — 2026-07-28 — Fila de duplicidades: 199 pares viraram 3

### Corrigido
- O RH pediu ação em massa nas duplicidades de jornada. **Medindo contra os
  dados reais, a fila tinha 199 pares e só 3 eram duplicata** — 80 eram o mesmo
  texto com horário diferente, 40 o mesmo horário com cliente diferente.
  Resolver "em massa" seria o merge cego que o módulo existe para impedir, e o
  estrago é invisível: a pessoa descobre no contracheque.
- Duas regras estruturais: **números diferentes ⇒ jornadas diferentes**;
  **mesmos números + letras diferentes ⇒ clientes diferentes**.
- Lição geral: quando o RH pede velocidade, conferir antes se a fila não está
  cheia de ruído — velocidade em fila errada multiplica erro.

## [2.11.0] — 2026-07-28 — Currículo em Word abria aba em branco

### Corrigido
- O log de abertura não dizia nada sobre o que falhou.

## [2.10.0] — 2026-07-28 — Ficha completa do talento

### Adicionado
- Painel na própria linha com tudo do cadastro, incluindo o `resumo` e a
  `origem` — que iam para o banco e ninguém via.

### Corrigido
- `.talento-form` perdia para `.cartao` por ordem de fonte e grudava o
  formulário na esquerda. No mobile passava despercebido.
- Sublinhado do menu (os itens viraram `<NavLink>` na v1.97) e chips
  sobrepostos.

## [2.09.0] — 2026-07-28 — Todos os e-mails do sistema viram texto editável

### Adicionado
- Migração completa dos e-mails externos para o catálogo.

## [2.08.0] — 2026-07-28 — Tela de Uniformes

### Adicionado
- O pedido era "um e-mail com todas as informações de uniforme"; a escolha foi o
  **contrário do pedido literal**, e combinada: nome, posto e medidas por e-mail
  é ficha de pessoal circulando em caixa que ninguém controla, e a cada 20
  admissões seriam 20 e-mails que o time para de ler. A lista fica na tela; o
  aviso diz só "fulano informou os tamanhos, veja em /rh/uniformes".
- Dispara no `concluir_envio`, **nunca no autosave** — o wizard salva a cada 900ms.

## [2.07.0] — 2026-07-28 — E-mails externos migram para os textos editáveis

## [2.06.0] — 2026-07-28 — Textos de e-mail editáveis pelo RH

### Adicionado
- Catálogo em `email_templates.py` como fonte da verdade; a tabela guarda só o
  que o RH escreveu por cima. Histórico append-only, preview, restaurar versão.
- **O template é apresentação, nunca decisão**: os e-mails que enumeram
  documentos recebem a lista pronta como `{{lista}}` — a regra do que entra
  continua no código.
- **Variável obrigatória valida no salvamento**: sem `{{codigo}}` num e-mail de
  acesso, a mensagem sai bonita e vazia e ninguém mais entra no sistema.
- **Fallback sempre**: sem registro, texto vazio ou erro de leitura vale o padrão
  — e-mail nenhum deixa de sair por edição ruim.

### Corrigido
- **Teste de e-mail não pode depender da redação**: o smoke extraía o OTP com
  `split("eletrônica é: ")`. Com o texto editável, uma edição no painel derrubaria
  o CI num commit sem relação nenhuma. Agora acha o código por padrão.

## [2.05.0] — 2026-07-28 — A opção de VT se confirma antes de assinar

### Corrigido
- A troca da opção existia só dentro do card, no meio da lista de documentos;
  quem não reparasse assinava errado — e o termo vira desconto de até 6% em
  folha, então o erro custa salário. A confirmação foi para logo acima de
  "Assinar os documentos", dizendo o efeito em dinheiro.

## [2.04.0] — 2026-07-28 — O candidato reabre o próprio envio

### Adicionado
- Depois do "CONCLUÍ MEU ENVIO" o checklist congelava e só o RH reabria — quem
  percebia na hora que mandou o arquivo errado ficava dependendo de socorro.
- Guarda: **qualquer** slot já revisado recusa com 409 — trocar arquivo já
  analisado faria a análise valer para um documento que não existe mais.

## [2.03.0] — 2026-07-28 — O acesso público para de morrer no app de e-mail

### Corrigido
- **Link de e-mail identifica, nunca autentica** (regra que rege `/creche` e
  `/meu`). O gate 2FA morria no webview: a pessoa abria o link, saía para ler o
  código — única forma — e voltava com a tela zerada. O backend guardava a sessão
  por 6h, mas o token vivia só em `useState`, e o front ainda apagava o `?t=`.
- Limpar o `?t=` da URL só **depois** de resolvê-lo — apagar antes era o que
  impedia o "voltar" de recuperar a tentativa.

## [2.02.0] — 2026-07-28 — O caminho de volta do candidato estava quebrado nas três pontas

### Corrigido
- **Todo e-mail que manda a pessoa voltar ao sistema leva o link junto**: os
  e-mails de rejeição diziam "acesse o mesmo link da sua admissão" e **não
  mandavam link nenhum**.
- **`catch` vazio anti-enumeração engolindo erro de infra**: `Entrar.jsx` mostrava
  "📬 Confira seu e-mail" **mesmo com HTTP 500** — sucesso mentiroso; a pessoa
  esperava um e-mail que nunca saiu. A resposta idêntica para CPF que existe e
  que não existe continua certa; 5xx tem que virar erro visível.
- Regra: **erro de negócio ≠ erro de infraestrutura**. Ao escrever `catch`
  silencioso, pergunte qual falha ele está escondendo.

---

## [2.01.0] — 2026-07-28 — Modelos de IA configuráveis e à prova de "`:free` sumiu"

Salvar a chave do OpenRouter mostrava "não respondeu ou recusou a chave"
mesmo com a chave correta.

### Corrigido
- **Modelo `:free` do OpenRouter é volátil.** `meta-llama/llama-3.3-70b-instruct:free`
  foi removido do catálogo do OpenRouter; chamar um modelo inexistente devolve
  404, que o painel exibia como "recusou a chave" — escondendo a causa real (a
  chave estava certa, o modelo é que sumiu).
- **Mensagem de erro do painel agora distingue os motivos.** "Recusou a chave"
  só aparece em 401/403; um 404 diz "modelo indisponível — confira os modelos" +
  dica da política de dados do OpenRouter. Baseado em `IndisponivelError.codigo`.

### Adicionado
- **Lista de modelos por provedor com fallback interno.** Cada provedor tenta
  seus modelos em ordem; se um falha (404, cota…), cai no próximo modelo do
  MESMO provedor antes de trocar de provedor. Só 401/403 pula o provedor inteiro.
  Padrões free novos, ambos com suporte a JSON (exigido pelo Match):
  `google/gemma-4-31b-it:free` → `openai/gpt-oss-20b:free`.
- **Modelos editáveis no painel** (Config → IA de texto): quando um id sumir de
  novo, o RH corrige em segundos, sem deploy. Chaves `openrouter_modelos`/
  `groq_modelos` na config dinâmica; vazio volta aos padrões do código.

## [2.00.0] — 2026-07-28 — Match de Vagas assíncrono e multi-provedor

Correção do incidente do mesmo dia: o RH ranqueou 131 talentos e só 18 foram
analisados; 67 segundos depois, na segunda tentativa, só 2. Plano completo e
diagnóstico em `docs/planejamento/10-match-vagas-assincrono.md`.

### Corrigido
- **Cota da IA derrubava a análise inteira.** Um HTTP 429 (limite de uso —
  transitório, resolve em segundos) era convertido no MESMO erro de um 401
  (chave inválida — permanente), e um `kill switch` irreversível pulava
  todos os talentos restantes. Agora `CotaExcedidaError` é distinto de
  `IndisponivelError`, o `Retry-After` do provedor é respeitado, e o worker
  espera e retoma em vez de desistir do lote.
- **Nada era persistido**: cada clique refazia as 131 análises e pagava tudo
  de novo — foi por isso que a 2ª rodada foi *pior* que a 1ª. Agora o
  resultado é gravado e reaproveitado; clicar de novo é praticamente grátis
  (botão "Reanalisar tudo" força quando você quiser).
- **Mensagem desonesta**: a tela dizia "IA indisponível", que o RH lia como
  "caiu, vou tentar de novo" — e o segundo clique piorava tudo. Agora diz
  que o limite de uso foi atingido e em quanto tempo tentar.
- **Currículo `.heic` (foto de iPhone) era 100% ilegível**: o upload aceitava,
  mas faltava `pillow-heif` e o erro era engolido. Também corrigido:
  currículo com `curriculo_nome` NULL (importados de planilha) caía em
  "formato desconhecido" mesmo com o arquivo certo no MinIO.
- **Todos os talentos ficavam "Novo" para sempre** — nada movia o status.
  Agora `novo → em_analise` quando o RH pratica um **ato de atenção**: abrir
  o currículo ou as anotações da pessoa. Deliberadamente **não** no
  ranqueamento em massa: marcar 131 de uma vez recriaria o mesmo problema
  com outro rótulo.

### Adicionado
- **Ranqueamento assíncrono** na fila Redis/RQ que já existia no ecossistema
  e estava ociosa desde a v1.83. O RH clica e continua usando o sistema; o
  worker processa devagar, esperando cota quando precisa. Resolve também o
  timeout de 60s do nginx, que 131 análises jamais respeitariam.
- **Cadeia de provedores de IA**: **OpenRouter principal → Groq reserva**. Se
  um falha ou estoura cota, o outro assume automaticamente.
- **Aba de Resultados** — prestação de contas, não barra de progresso. Cada
  pessoa aparece com o MOTIVO de estar onde está: analisado (com nota e
  justificativa), sem currículo, currículo ilegível (com o formato),
  aguardando IA, ou com alerta de trecho suspeito. Ninguém some em silêncio
  — mesma regra do lote de documento crítico.
- **Painel de leitura de currículos**: quantos talentos existem, quantos têm
  currículo, quantos foram lidos e quantos são ilegíveis. Se este número
  estiver baixo, o gargalo está aí e não na IA.
- **Texto do currículo extraído uma vez, no upload** (Mistral OCR com
  fallback local), guardado **já minimizado** (sem CPF/RG/telefone/e-mail/
  CEP) e reaproveitado em todos os ranqueamentos. Botão de backfill para os
  currículos que já estavam na base.
- **Dados do cadastro entram na análise** junto com o currículo (cargo,
  região, escolaridade, experiência informada) — pedido do Bruno.
- **Aviso interno por e-mail ao terminar**, pela matriz de eventos (evento
  novo `match_vagas_concluido`), nunca direto para o `smtp_from`.

### Técnico
- `app/models/match.py` (CurriculoTexto, ProcessamentoMatch, AnaliseTalento),
  migration `e6f7a8b9c0d1`; `app/services/fila.py` (primeiro uso real da fila
  RQ), `app/services/curriculo_indexacao.py`, `app/workers/match.py`.
- Testes novos: `test_ia_texto_cadeia.py` (7 cenários — 429 vs 401, fallback
  entre provedores, espera do worker, teste de chave no provedor certo) e
  `test_match_persistencia.py` (reaproveitamento sem chamar IA, `reanalisar`
  sem duplicar, cota sem sumir com ninguém, retomada). `test_match_vagas.py`
  reescrito para a arquitetura nova.
- Dois bugs pegos pelos próprios testes antes de ir ao ar: `reanalisar=True`
  violava a constraint `UNIQUE(vaga_id, talento_id)` ao reinserir em vez de
  atualizar; e a aba de Resultados ficava presa em "Carregando…" por um
  `useEffect` que se realimentava.

### Pergunta aberta
Quantos dos 131 talentos têm currículo anexado? O painel de leitura agora
responde isso na tela. Se forem poucos, o gargalo não é IA — é que quase
ninguém anexa currículo, e isso se resolve no formulário público.

## [1.99.0] — 2026-07-28 — Onda C2: Match de Vagas × Banco de Talentos

### Adicionado
- **Match de Vagas** (Recrutamento → 🧩 Match de Vagas): o RH cadastra a vaga
  (título, descrição, cargo, região, regime, salário, requisitos
  obrigatórios/desejáveis) e o sistema ranqueia os talentos do Banco de
  Talentos por aderência — filtro estruturado local primeiro (cargo/região,
  sem custo de IA), depois leitura do currículo pela IA (nota + justificativa
  em campos fixos). **A IA nunca decide sozinha**: ordena e explica; quem
  convoca é o RH. Resultado no DashPlanilha (ordenável, filtrável, com a
  justificativa no detalhe da linha).
- **Base legal LGPD verificada**: o termo do Banco de Talentos já autoriza
  "tratar os dados para fins de recrutamento" — cobre a triagem por IA
  (uso primário da finalidade, não secundário). Formulário público ganhou
  uma frase de transparência avisando que dados e currículo podem ser
  analisados por IA, com decisão final sempre do RH.
- **Minimização antes do envio à IA**: CPF, RG, telefone, e-mail e CEP são
  removidos do texto do currículo antes de qualquer chamada — nenhum desses
  ajuda a avaliar aderência a uma vaga.

### Segurança — currículo é entrada hostil
- Achado do próprio Bruno durante a revisão do roadmap (não estava no plano
  original): o currículo é upload público de gente desconhecida, e o texto
  extraído dele vai direto para dentro de um prompt de IA — é **entrada
  hostil**, não dado. Ataque real e documentado no mercado ("white text
  resume injection"): texto em fonte branca/corpo 1 no fim do currículo
  instruindo o modelo a dar nota máxima. É falha silenciosa (ranking
  adulterado parece idêntico a um legítimo) e questão de **justiça do
  processo seletivo** — quem sabe o truque passa na frente de quem não sabe.
- **5 camadas de defesa** (`services/anti_prompt_injection.py`), nenhuma
  sozinha resolve: delimitador aleatório por chamada, saída estruturada
  (JSON, nunca texto livre), teto de tamanho, detecção de padrão suspeito
  com **alerta visível ao RH** (nunca filtro em silêncio — mesmo princípio
  do lote de documento crítico), e texto invisível reportado como sinal.
  Currículo suspeito aparece marcado "⚠️ suspeito" no ranking, com o texto
  neutralizado antes de chegar à IA — nunca escondido do RH.
- Regra geral registrada no CLAUDE.md para todo texto de origem externa que
  chegar a um modelo daqui para frente: é dado, nunca instrução.

### Técnico
- `app/models/vaga.py`, `app/api/vagas.py`, migration `d5e6f7a8b9c0`.
- `app/services/curriculo_texto.py`: extração de texto (PDF via
  pypdf/Mistral OCR, imagem via Tesseract/Mistral OCR, DOC/DOCX via
  LibreOffice+PDF) + minimização de PII. Nunca inventa nota para currículo
  ilegível.
- `app/services/match_vagas.py`: orquestra filtro estruturado + análise por
  IA, usando `ia_texto.py` (Groq) e `anti_prompt_injection.py`.
- Testes novos: `test_anti_prompt_injection.py` (5 padrões de ataque
  detectados, 3 currículos limpos sem falso positivo, teto de tamanho,
  resistência a fechamento de delimitador) e `test_match_vagas.py` (prova
  que o prompt que chega à IA não contém o comando de ataque íntegro, mesmo
  com IA mockada "honesta" — a defesa está na preparação do texto, não no
  bom comportamento do modelo).
- Groq mantido nos dois módulos de IA (C1 e C2) — decisão consciente do
  Bruno, contra a recomendação inicial de provedor com retenção zero;
  minimização é a proteção que resta.
- Validado com Playwright contra ambiente efêmero: CRUD de vaga, ranking
  real (talento com cargo compatível sobe para o topo da lista), e teste
  end-to-end confirmando que o filtro estruturado funciona corretamente.

## [1.98.0] — 2026-07-28 — Onda C1: Minutário de Mensagens

### Adicionado
- **Minutário de Mensagens** (Recrutamento → 💬 Minutário de Mensagens):
  modelos de mensagem (CRUD) para WhatsApp/e-mail + composição assistida por
  IA (Groq). O RH preenche campos da VAGA (tom, cargo, regime, salário,
  local, escala, jornada, horário, requisitos obrigatórios/desejáveis,
  instruções, prazo) — **nenhum dado de candidato** entra na chamada à IA. O
  texto gerado sempre volta editável antes de qualquer envio: a IA propõe, o
  RH aprova. Envio por **copiar o texto** ou por um **link do WhatsApp**
  (`wa.me`) já com a mensagem pronta — sem integração com a API oficial do
  WhatsApp (decisão consciente: `wa.me` entrega o essencial sem o custo e a
  dependência de uma conta Business verificada).
  - Modelos reusam o catálogo de **tags** do mini-CRM para categorizar.
  - Groq configurável em Configurações → E-mail e integrações (mesmo padrão
    do OCR com Mistral: chave na config dinâmica, nunca devolvida, botão de
    teste de conexão).

### Técnico
- `app/services/ia_texto.py`: camada de geração de texto, provedor
  configurável (Groq por padrão) — usada também pelo Match de Vagas (C2).
  Trocar de provedor no futuro é mudar este arquivo só.
- `app/models/minutario.py`, migration `c4d5e6f7a8b9`.
- Bug pego pelo teste novo (`test_minutario_prompt.py`) e corrigido antes de
  ir ao ar: preencher **só** o campo Tom gerava um prompt sem nenhuma
  instrução de conteúdo (o fallback genérico só disparava quando também
  faltava o tom). Corrigido: o fallback dispara por falta de CONTEÚDO
  (campos da vaga ou modelo de referência), o tom é só estilo.
- Testado com Playwright contra ambiente efêmero: composição, erro amigável
  sem chave configurada, CRUD de modelo, e a tela de config do Groq.

## [1.97.0] — 2026-07-28 — Onda B: 16ª leva de feedbacks (3 itens)

### Adicionado
- **URL própria para cada tela do painel do RH** (react-router estava
  instalado mas nunca usado dentro de `/rh/*`): menu lateral agora usa
  `<NavLink>` (`/rh/colaboradores`, `/rh/config`…) e cada pessoa aberta ganha
  `/rh/candidato/<id>`. Isso resolve de graça o que o botão direito não
  oferecia — Ctrl+clique e "abrir em nova aba" funcionam porque o React
  Router intercepta só o clique simples. F5 na ficha de alguém mantém a
  mesma tela (antes sempre voltava para Admissões).
- **Modal (primeiro do projeto) para as anotações do mini-CRM**: o inline
  dentro da linha da tabela estava espremido (rolava na horizontal) — o
  sistema de design (`08-sistema-de-design.md`) foi revisado no *princípio*,
  não ganhou uma exceção: "editar perto do item" agora admite inline **ou**
  modal ancorado (quando há anexo + histórico + texto longo). O modal
  reaproveita o padrão de fechar do `SelectBusca` (clique fora, Escape),
  mostra o nome da pessoa no cabeçalho, e tem foco preso.
  - **Editar anotação** (antes só criar/excluir): `PATCH
    /rh/crm/anotacoes/{id}`. O autor original nunca é sobrescrito — grava-se
    o editor e a data à parte (`editado_por`/`editado_quando`).
- **Central de Importações** (Configurações → 📥 Importações): os 6 uploads
  de planilha do RH (Colaboradores, Postos, Jornadas ×2, Talentos, Ponto)
  saíram das telas de origem e agora vivem só aqui, com instruções e o que
  acontece com duplicados — nenhuma lógica de importação foi duplicada, só a
  UI foi centralizada. As telas de origem ganharam um link de cortesia. A
  Incidência de Benefícios (fluxo de 2 passos com decisões linha a linha) e a
  padronização de cargos/jornadas por texto colado continuam em tela própria
  — a central aponta para elas, não as reimplementa.

### Técnico
- `frontend/src/Modal.jsx`, `frontend/src/rh/Importacoes.jsx`.
- Migration `b3c4d5e6f7a8`: `crm_anotacao.editado_em`/`editor_nome`.
- Testado manualmente com Playwright contra ambiente efêmero: navegação por
  URL, F5 na ficha, modal (criar/editar/fechar por Escape e clique fora), e
  upload real de planilha de Postos pela central nova (118 postos criados).

## [1.96.0] — 2026-07-27 — Onda A: 16ª leva de feedbacks (3 itens)

Roadmap completo e revisão adversária (party-mode) em
`docs/planejamento/09-roadmap-feedbacks-16a-leva.md`. Ordem de execução
`A3 → A1 → A2` (torneira antes do balde: estanca a entrada de cargo digitado
livre antes de limpar o de-para em massa).

### Corrigido
- **Ficha do RH não salvava e não dizia o motivo** (bug silencioso): uma
  `ValidationError` do Pydantic era levantada FORA do ciclo de validação do
  FastAPI (o corpo da rota é um dict livre) e escapava como **HTTP 500 em
  texto puro** — o front não tinha detalhe algum para mostrar. Corrigido em
  6 frentes:
  - Handler global `@app.exception_handler(Exception)` em `main.py`: qualquer
    erro não tratado agora devolve `{"erro": "interno", "id": "<correlação>"}`
    — **nunca** o texto real da exceção (que pode conter o valor que estourou
    no banco, ex.: CPF).
  - `rh_ficha.py::editar_secao` captura a `ValidationError` e devolve 422 com
    `[{loc, msg, type}]`, e captura `DataError` do commit (coluna truncada:
    UF por extenso, CEP com hífen, tipo sanguíneo longo) nomeando o campo.
  - Normalização de entrada: UF vira 2 letras maiúsculas, CEP vira só dígitos,
    antes da validação — mesmo padrão que o CPF já tinha.
  - `api.js` para de descartar a lista estruturada de erros do Pydantic
    (`e.campos`), em vez de trocá-la pela string genérica `dados_invalidos`.
  - Mensagem de erro/sucesso passa a ser **local à seção** (`<details>`), não
    mais um banner ~19 blocos JSX acima do formulário e fora do viewport.
  - Corrigido também: sucesso não é mais mascarado como falha quando o
    recarregamento pós-salvamento falha (o `await carregar()` estava dentro
    do `try`).
  - Formulário ganhou os campos que faltavam para o RH destravar uma ficha
    presa na declaração final: sexo, identidade de gênero, cor/raça,
    nacionalidade, estado civil, escolaridade, PCD, logradouro/número/
    complemento separados. Datas viram `<InputData>` com máscara, enums e UF
    viram `<select>` — nunca mais texto livre para esses campos.

### Adicionado
- **Cargo do convite é lista com busca**, igual ao seletor já usado na ficha
  do colaborador — evita "Vigia"/"vigia"/"Vigía" virando cargos distintos.
  Só frontend; `cargo_funcao` continua string livre.
- **Padronização em massa de cargos e jornadas do Tirvu**: o RH cola o texto
  copiado da tela do Tirvu (Cargos ou Jornadas) em Configurações → Empresas e
  jornadas, o sistema PROPÕE o de-para (`CargoTirvu`/`Jornada.tirvu_id`) e o
  RH confirma linha a linha — nunca grava sozinho. Detecta e sinaliza (nunca
  funde): cópia parcial (contagem do cabeçalho não bate), cargos homônimos
  com 2+ IDs ativos no Tirvu, jornadas duplicadas após limpar a sujeira de
  "vínculos" colada na cópia. Ataca a causa raiz das pendências manuais do
  export em massa para o Tirvu.

### Técnico
- `app/services/importar_tirvu_txt.py`: parser puro (sem DB) do formato
  colado — testável isoladamente.
- Rotas `POST /rh/tirvu-txt/{preview,confirmar}-{cargos,jornadas}`.
- Testes novos: `test_editar_secao_rh.py` (os casos que viravam 500 mudo),
  `test_importar_tirvu_txt.py` (parser, validado contra os dados reais do
  RH), `test_importacao_massa_nao_regride_export.py` — exigido pela revisão
  adversária: gera o export do Tirvu antes/depois da importação em massa e
  garante que **só** a coluna Cargo muda, célula a célula.

## [1.92.0] — 2026-07-24 — Onda Admissão/Ficha (6 ajustes)

### Adicionado / Corrigido
- **Cargo obrigatório no link**: o convite passa a exigir o cargo/função (422
  `cargo_obrigatorio`) — o cargo casa por texto com modelos/provas/arquivo.
- **Informativo de integração só após o RH disparar**: o informativo (efetivo
  INFRAERO e intermitente) NASCE bloqueado e só vai ao candidato assinar quando
  o RH clicar "📨 Liberar" no painel (`aguardando_liberacao`). Enquanto isso,
  não aparece no fluxo de assinatura. Vale para os dois regimes.
- **Autodeclaração de residência**: quando o comprovante não está no nome do
  candidato, ele marca no wizard, informa o titular e a relação (pai/cônjuge/
  locador…) e assina uma autodeclaração — que só é exigida nesse caso.
- **Instrução do salário do intermitente**: no campo de salário (ficha), uma
  nota aparece só quando o regime é intermitente: informe o valor/dia = salário
  do cargo ÷ 30.
- **Vários documentos no mesmo tipo (insert manual do RH)**: ao inserir um
  documento manualmente, o RH pode selecionar vários arquivos de uma vez (ex.:
  RG frente+verso, ou os documentos certos no lugar dos errados) — viram um PDF
  combinado, como no envio do candidato.
- **Matrícula do Tirvu protegida**: reimportar do Tirvu com a coluna "matrícula"
  vazia não zera mais a matrícula existente (999NNNN ou a real) — só sobrescreve
  quando vem preenchida. Espelha a proteção que já havia para o nome.

### Técnico
- `assinatura.aguardando_liberacao`, `endereco.comprovante_titular`/
  `comprovante_relacao`, enum `documento_assinavel += autodeclaracao_residencia`.
  Migration `e6a8c0d2f4b1` (reversível). Gerador `gerar_autodeclaracao_residencia`.

## [1.91.0] — 2026-07-24 — Telemetria das provas visível no RH

### Corrigido/Melhorado
- **O relatório de comportamento das provas agora aparece.** A telemetria (troca
  de aba/app, tempo fora da tela, tentativas de print, copiar/colar, quedas de
  conexão) já era coletada durante a prova, mas só existia no banco — não era
  exibida (feedback do Bruno: "por que não aparecem os dados de telemetria?").
  Agora:
  - **No dash de aplicações**: coluna "Comportamento" com um selo (✓ limpo / ⚠️ N)
    e o detalhe no tooltip; ordenável pela quantidade de alertas.
  - **No detalhe da aplicação**: card "🖥️ Comportamento na tela" com o relatório
    completo (cada métrica, destacando as que têm ocorrência).
- É **indício**, não prova de fraude — o RH decide; nunca vira nota.

## [1.90.0] — 2026-07-24 — Banco de Itens (Provas Fase 2)

### Adicionado
- **Banco de Itens**: questões REUTILIZÁVEIS, catalogadas por **cargo**,
  **senioridade** (Júnior/Pleno/Sênior/Qualquer) e **tags** de conteúdo. A ideia
  é tornar a confecção de provas ESCALÁVEL — catalogar uma vez, montar provas
  rápido. Nova aba em Provas (🗃️ Banco de itens) com CRUD e filtros.
- **Montar prova a partir do banco** (na tela de edição da prova, "🗃️ Adicionar
  do banco"): dois modos — **escolher item a item** (com filtros) ou **sortear**
  N itens por cargo/senioridade/tag. Em ambos, o item é **copiado** para a prova
  (snapshot): editar ou excluir o item no banco depois **não altera** provas já
  montadas nem aplicações em andamento.
- **Promover questão → banco** ("→ banco" em cada questão da prova): reaproveita
  uma questão já escrita, copiando-a para o banco (a original permanece na prova).

### Preserva o que existe (pedido do Bruno)
- Migração **ADITIVA** (`item_banco`, nova tabela) — NÃO toca `prova_cargo` nem
  `questao_prova`. As provas existentes continuam idênticas, nada é desmontado.
- Migration `d4f6b8a0c2e1` (reversível). Senioridade é lista fixa (não texto
  livre, para filtrar sem "pleno"/"Pleno"/"PL"). Tags do item são próprias
  (conteúdo), separadas do catálogo de tags de PESSOAS do CRM.

## [1.89.0] — 2026-07-24 — Provas-avançado Fase 1: aleatorização, duplicar, explicação

### Adicionado
- **Aleatorização das provas** (interruptor por prova): embaralha a ordem das
  questões E das alternativas para cada participante, com semente ESTÁVEL por
  aplicação — recarregar a página não reembaralha (o candidato não se perde). A
  correção casa por id da opção, então embaralhar a exibição **nunca altera a
  nota** (testado). Prova didática com sequência proposital fica com o
  embaralhamento desligado.
- **Explicação da resposta** (campo opcional por questão) + **flag por prova**
  "mostrar ao participante". Ao terminar, se a prova permite, o participante vê
  uma revisão com o gabarito e a explicação de cada questão (didática). Prova de
  seleção fica com a flag desligada e a revisão é bloqueada (403) — o gabarito
  nunca vaza. A nota continua restrita ao RH em qualquer caso.
- **Duplicar prova inteira** e **duplicar questão**: clona título/config e todas
  as questões (com gabarito e explicação); a cópia da prova nasce como "(cópia)"
  sem links/aplicações. Botões na lista de provas e em cada questão.

### Técnico
- `prova_cargo.embaralhar`/`mostrar_explicacao`, `questao_prova.explicacao`,
  `aplicacao_prova.seed`. Migration `c3e5a7f9b1d2` (reversível, sem enum).
- Embaralhamento determinístico por seed (`_publicas_ordenadas`): sub-seed por
  questão para as opções não permutarem todas igual. Rotas novas:
  `/rh/provas/{id}/duplicar`, `/rh/provas/{id}/questoes/{qid}/duplicar`,
  `/p/{token}/a/{aid}/revisao`.
- **Banco de itens por cargo/senioridade fica para a Fase 2** (rearquitetura: a
  questão deixaria de pertencer a uma única prova).

## [1.88.0] — 2026-07-24 — Máscara de data centralizada + filtros compactos

### Corrigido (dado / risco)
- **Máscara de data `dd/mm/aaaa` em todo campo de data digitável.** O campo de
  nascimento da criança na creche (link público e wizard) era input LIVRE sem
  máscara — dava para salvar "20122025" cru como data (bug relatado: nascimento
  de filho de brigadista gravado errado). Agora todo campo de data usa o
  componente central `<InputData/>`, que insere as barras conforme digita e
  **valida que a data existe** (rejeita 31/02, ano absurdo, data incompleta),
  guardando ISO por baixo. As duas máscaras que existiam duplicadas e privadas
  (Wizard, Portal) foram unificadas nesse componente + helpers em `fmt.js`
  (`fmtDataBR`/`isoParaBR`/`brParaISO`), espelhando o padrão de CPF/telefone.

### Melhorado (UX)
- **Barra de filtros do RH compacta.** Antes cada filtro ocupava uma linha
  inteira; agora é uma GRADE (vários por linha, rótulo pequeno em cima),
  aproveitando o espaço sem virar bagunça. Como todas as listas do RH usam o
  DashPlanilha, a mudança vale para todas de uma vez (Jornadas, Colaboradores,
  Talentos, Provas, Creche, Desenvolvimento…).
- **Todo filtro de seleção agora tem busca-ao-digitar.** Os `<select>` nativos
  da barra viraram `SelectBusca` — começa a digitar e a lista filtra ("filtro é
  algo funcional"). Os de texto já filtravam ao digitar.

## [1.87.0] — 2026-07-24 — Mini-CRM: anotações e tags no ciclo de vida

### Adicionado
- **Anotações e tags que acompanham a pessoa** por todo o ciclo de vida
  (talento → candidato → efetivo → desligado). A memória é feita uma vez e
  "segue a pessoa" sem cópia: como o talento é preservado e ligado ao candidato
  por `candidato_id`, as consultas juntam os dois lados (OR em `services/crm.py`).
- **Anotações**: texto livre + AUTOR (quem lançou, snapshot do nome) + data/hora
  + anexo opcional (MinIO). Registro de comunicação interna do RH, visível a
  toda a equipe. Excluível.
- **Tags**: catálogo com CRUD (Configurações → 🏷️ Tags): nome + cor + ativa.
  Marcar/desmarcar na pessoa; filtro e coluna no dash do Banco de Talentos.
  Catálogo único evita "entrevistado"/"Entrevistado" virarem tags diferentes.
- **Onde aparece**: painel na própria linha do dash de Talentos (botão
  🗒️ Anotações) e seção recolhível na ficha do candidato/colaborador
  (`Detalhe.jsx`). Componente único reutilizável `MemoriaPessoa.jsx`.

### Técnico
- Tabelas `crm_tag`, `crm_pessoa_tag` (N:N, 2 FKs opcionais talento/candidato),
  `crm_anotacao`. Migration `b7c4d9e1f2a3` (reversível). Sem enum novo.
- Rotas `/rh/crm/...` (todas restritas ao RH). Tags carregadas em lote no dump
  de talentos (sem N+1). Autor via `requer_rh` (`rh.id`/`rh.nome`).

## [1.86.0] — 2026-07-23 — Sistema de design + padronização + bugs de provas

### Sistema de design (a dor nº1: "toda hora tenho que padronizar")
- **Documento de padronização e identidade**
  (`docs/planejamento/08-sistema-de-design.md`): o guia canônico de padrões —
  tokens (os `--esp-*`/`--fs-*` já existiam, faltava USÁ-los), primitivas de
  layout, dark mode, editar-na-linha, overflow, toggle, tooltips, checklist de
  tela nova. Tela nova nasce padronizada porque consome o sistema.
- **Primitiva de página `.pagina`**: os módulos novos (Desenvolvimento,
  Desempenho, Avaliações) renderizavam `<section>` cru sem padding lateral e
  ficavam "sem respiro". Agora usam `.pagina` (= `.rh-painel`), com respiro.
- **Dark mode — menu suspenso legível**: faltava `color-scheme` no tema; o
  dropdown nativo do `<select>` vinha claro sobre o app escuro (ilegível).
  Corrigido em `:root` e `:root[data-tema='escuro']`.
- **Editar abre PERTO do item**: em Desenvolvimento → Tipos, editar abria no
  topo; agora o formulário substitui o card sendo editado.
- **Histórico que recolhe e não estoura**: o "ver histórico de decisões" (Creche)
  virou toggle; a auditoria (Configurações) ganhou rolagem contida e quebra de
  texto — a coluna JSON não estoura mais a margem da tela.

### Provas — 3 correções
- **Questão discursiva**: o botão "＋ Questão discursiva" caía no formulário de
  objetiva (nascia sempre objetiva). Agora abre o formulário certo (só
  enunciado).
- **Pontuação no dash**: prova só-objetiva concluída mostrava a nota das
  objetivas mas a **nota final ficava "—"** (só era calculada ao corrigir
  discursivas). Agora a nota final é gravada na conclusão quando não há
  discursivas.
- **Timer no celular**: ao trocar de app, o contador "parava" (era o relógio
  visual congelando). Agora deriva de um instante-alvo absoluto e
  re-sincroniza com o servidor ao voltar o foco.

### Análise entregue
- **Central de Ajuda** (`docs/planejamento/09-central-de-ajuda-analise.md`):
  comparativo GitBook vs. Notion/Docusaurus/MkDocs/Document360/Confluence etc.,
  com custos atuais e recomendação para equipe de uma pessoa só.

## [1.85.0] — 2026-07-23 — Import de ponto + interruptor do atestado

### Adicionado
- **Import de ponto do Tirvu como CONTEXTO da avaliação** (RH → Fatos
  Observados → Importar ponto): upload do `.xlsx` de ponto eletrônico, agregado
  por pessoa/período (`ResumoPonto`) e mostrado ao lado do formulário de
  avaliação — **nunca como nota automática**. Decisão de projeto para evitar
  "atraso vira número, número vira nota, nota vira desligamento".
- **Interruptor da leitura de atestado de saúde** (Configurações → OCR com IA):
  liga/desliga pelo painel a leitura por IA do atestado, que é dado sensível.
  Desligado por padrão; só deve ser ligado após a Mistral aprovar o Zero Data
  Retention no plano Scale (a trava vive no código, `ocr_roteador`).

### Decisões de dados (evitam injustiça)
- **Registro incompleto ≠ falta**: `00:00` de horas COM marcação de entrada é
  esquecimento de bater a saída, não ausência. Nos dados reais de 1 mês são 28
  incompletos contra 1 falta — tratar tudo como o Tirvu apurou acusaria 28
  pessoas injustamente.
- **`Horas Trabalhadas` é a fonte de verdade**, não as batidas (há dia sem
  batida e com horas apuradas). Casamento por **matrícula** (não há CPF na
  planilha), normalizando zeros à esquerda. Geolocalização e foto do ponto
  **não** são lidas (desproporcional para avaliação — LGPD).

## [1.84.0] — 2026-07-23 — Onda C: Avaliação de Desempenho

Digitaliza a Cartilha do Avaliador (17/06/2026) que rodava no Microsoft Forms.

### Adicionado
- **Fatos Observados**: a liderança registra na hora o que o colaborador fez
  (bom ou ruim), com fato e impacto — antídoto do efeito de recência. **O
  colaborador vê os fatos sobre ele** (portal `/meu`), mas **nunca o autor**.
  Rodam sozinhos e alimentam o formulário depois.
- **Formulário da cartilha** (11 seções, 7 indicadores, 8 competências, 5
  recomendações) com os fatos do período ao lado. Máquina de estados que **não
  deixa pular o feedback presencial**: rascunho → preenchida → feedback dado →
  manifestada → homologada.
- **Manifestação do colaborador** (seção 9, direito de resposta) no portal, com
  prazo de 7 dias — sem prazo, bastaria homologar antes de a pessoa ler.
- **Avaliação 360**: vertical (liderança, identificada) e horizontal (pares,
  **anônima e agregada** — o avaliado nunca vê o colega; o radar suprime a média
  dos pares com menos de 2 respostas).
- **Radar** ("teia") em SVG + **timeline** das médias na ficha da pessoa.
- **Calibração**: o desvio do avaliador INFORMA o homologador ("dá em média 4,0;
  os demais dão 3,6 — mais generoso") **sem alterar nota**. Distribuição forçada
  foi vetada; normalização com N pequeno é ruído.
- **Ciclos** (4 por ano, datas configuráveis) para agrupar as avaliações.

## [1.83.0] — 2026-07-23 — Onda B: Portal do Colaborador + Desenvolvimento

### Adicionado
- **Portal do colaborador `/meu`**: UMA porta para tudo que é da pessoa —
  cursos, certificados, pendências, avaliações. Gate do creche extraído (CPF →
  2FA por e-mail; sem e-mail, KBA), agora amarrado ao colaborador. A home é a
  lista de pendências dela, não um menu.
- **Cadastro de Desenvolvimento**: cursos, certificações e reciclagens ao longo
  do vínculo. Tipo configurável com validade, criticidade e cargos aplicáveis;
  herança do prazo em três níveis (posto > cargo > tipo). Leitura por IA
  pré-preenche; a pessoa confere.
- **Brigadistas NÃO é módulo — é uma consulta**: certificação crítica vencendo,
  com aviso automático 90 dias antes (worker), dash de quem está pronto, e
  montagem do e-mail de matrícula à Multicursos (individual ou em grupo, com o
  dossiê de cada um em PDF único).
- **Fila de validação do RH** com aprovação em lote para o caso fácil —
  documento crítico nunca entra no lote, e o lote diz quem barrou.
- **IA roteada por sensibilidade**: documento de saúde (atestado) só é lido com
  o Zero Data Retention ligado; identidade e certificado seguem normalmente.

## [1.82.0] — 2026-07-22 — Onda A: ajustes de campo

### Adicionado
- **Matriz de notificações** (evento × destinatários): cada aviso do sistema
  tem sua própria lista de e-mails, com herança de um padrão global. Corrige o
  aviso de "candidato concluiu o envio" que ia para a caixa de login do RH.
- **Creche — link direto na devolução, sem 2FA**: o e-mail de devolução leva um
  link de uso único (7 dias) que abre só a tela de correção; o e-mail já é
  comprovado, então refazer o código era atrito que fazia a correção não voltar.
- **Cargo/função clicável** na ficha: escolhe da lista de cargos já usados
  (evita "Vigia"/"vigia"/"Vigía") ou digita um novo. Continua texto livre.
- **Registra Ponto** vira pendência do export Tirvu (em branco, o Tirvu aceita
  calado e o colaborador nasce sem a marcação).

## [1.81.0] — 2026-07-22
### Adicionado
- **Colaboradores mostra o que falta no cadastro**: completude dos importados do
  Tirvu, para o RH ver de relance quem precisa de dado antes de exportar de volta.

## [1.76.0–1.80.0] — 2026-07-21/22 — DashPlanilha vira o padrão das listas
### Mudado
- **Colaboradores, Admissões e Creche migraram para o `DashPlanilha`**:
  ordenação por qualquer coluna, filtro por coluna, seleção + ações em massa,
  colunas configuráveis e export CSV — com cards de métrica clicáveis que
  ativam filtros. Os filtros pesados (posto, busca, status) ficam fora do dash,
  no topo, alimentando os dados; o dash refina em memória por cima. Passou a ser
  o padrão de TODA lista nova do RH.
- **Creche — "mais filhos" sem virar 1:N** (v1.79): reabrir o benefício ativo
  para acrescentar criança, em vez de largar o `candidato_id unique` e mexer em
  assinatura/dossiê.
### Corrigido
- Cards de Admissões aparecem mesmo com a lista vazia (v1.80, consertou o CI).

## [1.73.0–1.77.0] — 2026-07-21 — Reembolso-Creche: Ondas A/B/C

### Adicionado
- **Comunicação de estado + saídas** do creche: toda decisão avisa o colaborador
  por e-mail; **devolver** (reabre a edição), **indeferir** (terminal),
  **"não faço jus"** (some da fila mas fica no relatório), **suspender/encerrar**,
  e **desligar o colaborador encerra o benefício ativo**.
- **KBA nativa**: o gate serve os importados do Tirvu (sem ficha) usando dados
  imutáveis do cadastro (nascimento + sobrenome), não as fichas de admissão.
- **Não-respondentes e histórico** no dash, para provar que o elegível foi
  consultado e não pediu.

## [1.70.0] — 2026-07-20 — Jornadas estruturadas
### Adicionado
- Submenu **Jornadas** com parser que PROPÕE a estrutura (escala, horários,
  turno, adicional noturno, intrajornada, cargo) a partir da descrição — o RH
  confirma, nunca auto-grava. Sinalizador de duplicidade que só AVISA pares
  suspeitos (nunca funde: há ~40 erros de digitação nos dados reais). A
  `descricao` continua canônica — é ela que vai ao Tirvu.

## [1.69.0] — 2026-07-20 — `status` é só fluxo; `situacao` é só vínculo

### Mudado
- Separados os dois campos que compartilhavam `ativo`/`desligado` e confundiam
  as telas. Agora: **`status`** é só a fase do funil (convidado → … → aprovado/
  importado); **`situacao`** é só o vínculo (nulo = admissão, ativo, desligado).

### Legado
- Os valores **`ativo` e `desligado` do enum `StatusCandidato` ficaram ÓRFÃOS**
  (não se escreve mais). Não são removidos porque o Postgres não apaga valor de
  enum sem recriar o tipo; o front (`status.js`) já os ignora. **Não usar em
  código novo, não fundir os campos.**

## [1.63.0] — 2026-07-21 — Admissões e Colaboradores não vazam mais

### Corrigido
- **Cada registro aparece numa tela só**: Admissões filtra `situacao IS NULL`,
  Colaboradores filtra `situacao IS NOT NULL` (antes o mesmo registro vazava nas
  duas). Escapes simétricos para os casos de fronteira.

## [1.51.0] — 2026-07-20 — Reembolso-Creche (módulo completo)
### Adicionado
- Módulo do Reembolso-Creche (IN SEGES/MGI 147/2026): elegibilidade por posto,
  link público sem enumeração de CPF + KBA, assinatura colaborador→RH pelo
  multi-signatário, RH vê os documentos de cada criança, datas centralizadas e
  importador da planilha de incidência de benefícios (assistido).

## [1.55.0–1.61.0] — 2026-07-20 — Talentos, provas e imports

### Adicionado
- **Banco de Talentos** repaginado (wizard de 3 passos + currículo opcional),
  com dash próprio, envio de teste avulso e importação da planilha do Microsoft
  Forms (idempotente).
- **Provas por cargo**: banco de provas configurável pelo RH (objetivas com
  correção automática + discursivas), aplicação pública `/p/{token}`, correção
  no dash. Gabarito nunca vai ao público.

## [1.48.0–1.50.0] — 2026-07-19 — E-mail M365/Gmail em produção
### Corrigido
- **Callback OAuth** (Microsoft 365 e Gmail) passou a usar `https` quando o
  proxy não envia `X-Forwarded-Proto`, e a respeitar o `CF-Visitor`/host público
  atrás do Cloudflare — sem isso o login OAuth quebrava em produção.
- Rota de diagnóstico `/api/diag/callback` e versão no `/health` para confirmar
  qual imagem está no ar.

## [1.47.0] — 2026-07-19

### Mudado
- **"Exportar p/ Tirvu" saiu de Admissões e foi para Colaboradores**: só se
  manda para o Tirvu quem já virou colaborador (foi efetivado) — quem ainda
  está preenchendo a ficha não tem vínculo a criar lá. A planilha traz apenas
  quem **veio da admissão**; os importados do próprio Tirvu ficam de fora
  (já existem lá e seriam ignorados por ele).

## [1.46.0] — 2026-07-19

### Adicionado
- **Exportação de admissões para o Tirvu** — planilha no layout oficial de
  importação (28 colunas em ordem fixa), individual (botão na ficha) e em massa
  (respeitando os filtros da tela). Pré-checagem antes do download:
  o Tirvu recusa linha sem CTPS/PIS, e o RH fica sabendo aqui, não lá. Toda
  exportação é auditada (quem baixou, quantas linhas, quais postos).
- **CTPS Digital calculada** — número = o próprio CPF (11 dígitos), série =
  0000 (padrão eSocial). Preenchida sozinha quando o candidato informa o CPF;
  aparece na ficha cadastral só para os novos (quem já assinou não é afetado).
- **Empresas e Jornadas** como cadastros próprios (Configurações → Empresas e
  jornadas): o RH escolhe ou cria na hora, na ficha do colaborador. Jornadas
  importáveis da planilha de escalas do Tirvu (96 abas = 96 postos; as
  descrições do posto escolhido aparecem primeiro no seletor). "Registra ponto"
  por colaborador.
- **Endereço separado** (logradouro / número / complemento) na coleta nova,
  como o Tirvu pede. Endereços antigos migram por **backfill assistido**: o
  sistema propõe a separação e o RH confirma — nada muda sozinho.
- **Laudo PCD na ficha** — CID, tipo de deficiência, data do laudo e
  médico/CRM (Lei 8.213/91), coletados no formulário de quem se declara PCD.
- **Dependentes em bloco rotulado** na ficha cadastral (antes uma linha só).

### Corrigido
- Observação da CTPS na ficha dizia "7 primeiros dígitos + 4 últimos" —
  contradizia o padrão eSocial usado; corrigida.
- Planilhas enviadas ao RH (colaboradores, postos, jornadas) agora descartam o
  arquivo temporário do servidor imediatamente após o processamento.

## [1.44.0] — 2026-07-19

### Adicionado
- **Identidade visual configurável** (Configurações → Identidade visual): nome,
  razão social, CNPJ, endereço, contato, **logo e favicon** editáveis pelo
  painel. Aparecem nos PDFs, e-mails e no painel; os dados da Green House viram
  só o valor-padrão inicial. Desvincula o sistema de uma empresa específica.
- **Central de assinaturas** como menu próprio, com abas: documentos dos
  candidatos (dashboard de **todas** as assinaturas sem entrar em cada admissão),
  aguardando minha assinatura, já assinei, gerenciar roteiros, e papéis/
  assinantes/ordem.
- **Ordem das fichas de assinatura configurável** pelo RH (antes fixa no código).

### Mudado
- **Menu lateral reorganizado** por seções (Admissão, Documentos, Avaliação,
  Benefícios, Recrutamento, Sistema), sempre expandido e rolável — removida a
  versão hover/recolher que bugava. **Modelos** e **Assinaturas** saíram de
  Configurações e viraram menus próprios. Botão "Novo candidato" movido para a
  página de Admissões.

## [1.42.0 – 1.43.0] — 2026-07-19

### Adicionado
- **Multi-signatário**: um documento pode exigir a assinatura de vários em
  **ordem de papéis** — colaborador (link mágico), usuário do RH (assina logado,
  com senha) e/ou externo (link próprio + código, token de uso único e PDF só
  após 2FA). O PDF final consolida todas as assinaturas, com um manifesto
  multi-assinante e QR por etapa. Verificação pública por etapa.
- **Assinatura da equipe por autorização prévia registrada** (nunca carimbo
  falso): o representante confirma uma vez por código; sua assinatura passa a
  constar nos documentos daquele modelo, com validade e revogação.
- **Roteiro-padrão** de papéis por modelo; worker de **expiração** de roteiros
  vencidos + higienização LGPD de dados de externos não assinados.

## [1.38.0 – 1.41.0] — 2026-07-18/19

### Adicionado
- **Menu Arquivo**: inventário com filtros, download individual e **backup em
  lote** (ZIP por posto/pessoa + planilha XLSX), auditado com a lista de quem
  foi exportado.
- **Links de testagem avulsa** (`/t/{token}`): a pessoa entra só com o nome e vê
  o próprio resultado; **dashboard unificado de testes** (admissão + testagem)
  com reset e relatório de comportamento.
- **Modelos de documento completos**: opções por modelo (enviar por e-mail,
  exigir assinatura, papel do signatário), envio pontual para qualquer pessoa,
  predefinições (Ofício, Comunicado, Contrato, Declaração), papéis de assinatura.
- Testes do candidato editáveis após o convite; tooltip com o significado de
  cada palavra do DISC.

### Mudado
- Configurações reorganizada em submenus; UX desktop em cards (grade de 2
  colunas).

### Corrigido / Segurança
- **Rate limiting** em login (por IP e por conta), 2FA dos testes e da creche,
  recuperação de senha e solicitação de código de assinatura.
- **CPF sem máscara** nas telas internas do RH (máscara mantida no verificador
  público, nos logs e no envio à IA).
- **Trava anti-duplo-clique**: idempotência no servidor (dossiê, notificar,
  efetivar) — o 2º clique concorrente recebe 409; overlay de "processando" no
  cliente com atraso de 400 ms.

## [1.22.0 – 1.37.0] — 2026-07-17/18

### Adicionado
- **Reembolso-Creche** (IN SEGES/MGI 147/2026): adesão na admissão + link
  público de levantamento com 2FA e dossiê.
- **Base colaborador-cêntrica**: importação idempotente do Tirvu (.xlsx),
  colaboradores/postos, efetivar/desligar/transferir.
- **Testes DISC e situacional** na admissão, com telemetria de comportamento.
- **Lixeira universal** com restauração e retenção configurável.
- **Modelos de documento** no papel timbrado com variáveis; kit da Presidência;
  ficha do intermitente; campos de CNH/militar/dependentes.

### Corrigido
- Diversos feedbacks de campo: PDFs sem estouro de linha, DISC orientado, ficha
  completa, sincronização de nomes do Tirvu.

## [1.16.0] — 2026-07-17

### Adicionado
- **Notificações no Microsoft Teams**: em Configurações, o RH cola a URL de um
  Incoming Webhook (ou fluxo do Power Automate que posta no Teams) e escreve um
  **template** com variáveis (`{{nome}}`, `{{cargo}}`, `{{posto}}`,
  `{{status}}`…). Na tela do colaborador, o botão **Enviar ao Teams** posta a
  mensagem preenchida no canal. Sem OAuth — mesmo espírito do webhook de e-mail.

### Corrigido
- Cadastro público do Banco de Talentos falhava quando o e-mail era deixado em
  branco (o `EmailStr` recusava string vazia); agora vazio vira "sem e-mail".

## [1.15.0] — 2026-07-17

### Adicionado
- **Banco de Talentos**: formulário **público** (`/banco-de-talentos`, também
  linkado no portal) onde interessados deixam nome, contato, cargo pretendido,
  cidade, escolaridade e uma apresentação — protegido por honeypot anti-spam.
  No painel, uma aba **Banco de Talentos** lista os cadastros com filtros
  (status, cargo, busca livre), triagem de status e o botão **Converter em
  candidato**, que cria o cadastro migrando os dados já preenchidos, dispara o
  link de admissão e abre a ficha do novo candidato.

## [1.14.0] — 2026-07-17

### Adicionado
- **Módulo de criação de documentos (CRUD)**: o RH cria/edita documentos do
  zero em Configurações, já no papel timbrado padrão, com **variáveis
  dinâmicas** (`{{nome}}`, `{{cpf}}`, `{{cargo}}`, `{{posto}}`, `{{salario}}`,
  `{{data}}`…). Cada modelo pode ser vinculado a **qualquer colaborador**, a um
  **cargo** ou a um **posto**; na tela do colaborador aparecem os modelos
  aplicáveis com um botão **Gerar** (PDF preenchido no timbrado). Prévia
  disponível com os placeholders visíveis.
- **Todo PDF enviado vai para o papel timbrado A4** (decisão do RH): cada
  página do original é reduzida proporcionalmente e centralizada no corpo da
  página timbrada, sem distorcer. A leitura de texto (OCR e data do
  comprovante) passou a usar sempre o PDF original.

### Alterado
- Raiz do sistema virou um **portal com três portas** (Sou Candidato / Sou RH /
  Verificar documento) e há uma **entrada pública de verificação** (`/verificar`)
  onde se digita o código do registro.

## [1.12.0] — 2026-07-17

### Adicionado
- **Cargo, salário base e adicionais na ficha de cadastro**: o RH digita o
  salário à mão (texto livre) e adiciona quantos adicionais quiser (nome +
  valor em R$ ou %) na tela do posto; tudo passa a constar automaticamente na
  Ficha Cadastral do Colaborador. Alterar cargo/salário/adicionais de uma
  ficha já assinada a reabre para o colaborador assinar a versão atualizada
  (invalidação historizada, nunca deleção).
- **Colaborador troca a opção pelo Vale-Transporte** direto na tela de
  assinatura, enquanto o Termo de VT não foi assinado; depois de assinado, a
  troca é bloqueada (exigiria nova assinatura).

### Alterado
- **Marca d'água "GREENHOUSE"** (arte oficial que existia mas não era usada)
  agora aparece esmaecida na borda direita de todos os PDFs timbrados: fichas,
  ofícios, manifesto e páginas geradas a partir de fotos recebidas.

### Infraestrutura
- Os dois workflows de CI viraram um só (`ci.yml`, jobs `imagens` +
  `testes-de-interface`): cada commit aparece uma vez na lista de Actions.

## [1.10.0] — 2026-07-17

### Adicionado
- **Envio de e-mail via Power Automate (webhook)** como caminho "plug and play"
  para locatários do Microsoft 365 em que o admin bloqueia SMTP autenticado e
  registro de aplicativo: o RH cola a URL de um fluxo HTTP e o sistema manda o
  e-mail em JSON (com anexos em base64) para ele. Entra na cadeia de envio como
  Microsoft 365 → Google → **Power Automate** → SMTP, com card próprio no painel
  (passo a passo do fluxo e teste de envio). O envio OAuth direto via Microsoft
  Graph já existia e continua sendo a opção recomendada.

## [1.9.0] — 2026-07-17

### Adicionado
- **Frente e verso à prova de falhas**: nos documentos de duas partes (RG,
  reservista, CNH) o envio é passo a passo, um arquivo por vez — o seletor perde
  a seleção múltipla, acabando com o erro de quem tentava mandar os dois juntos.
- **Editor de imagem** (sem bibliotecas externas, para não pesar no aparelho de
  quem tem pouca internet): recorte com folga de segurança de 18% além da
  moldura já usada para alinhar, cantos arrastáveis (mouse e toque) e rotação de
  90° para a foto que saiu deitada. Vale para a foto tirada e para a imagem
  enviada do aparelho. Botão "Voltar" claro na câmera e no editor.

## [1.8.0] — 2026-07-17

### Corrigido
- **PDF não abria no Chrome do Android** (fundo escuro com um botão "Abrir" sem
  ação): o RH passa a ver os documentos por um visualizador em canvas (pdf.js)
  **apenas no celular** — no desktop segue o visualizador nativo do navegador.
- **Erros de upload** deixavam de virar um "sem conexão" genérico: queda real de
  rede, arquivo grande demais (413), formato inválido e erro de validação agora
  têm mensagens próprias e específicas.
- **Cabeçalho timbrado** dos documentos: arte alinhada à direita e título do
  documento centralizado.

## [1.7.0] — 2026-07-16

### Adicionado
- **Acordo de Confidencialidade** como quarta ficha de todo candidato,
  **retroativo**: quem ainda não assinou (mesmo já aprovado) passa a dever a
  assinatura automaticamente — o link de sempre abre direto na tela de
  assinar, e o dossiê passa a incluí-lo. Texto do modelo oficial com
  qualificação puxada dinamicamente da ficha (nome, CPF, nome social, função),
  endereço da sede unificado com o do rodapé, formatação uniforme no papel
  timbrado e gramática revisada (concordâncias, vírgulas, "resultará").

### Alterado
- OCR com IA (Mistral) passou a ser o **primeiro** degrau da leitura para
  qualquer arquivo (antes: só quando o PDF não tinha camada de texto);
  fallback: camada de texto do PDF → Tesseract local.

### Corrigido
- Busca no relatório de colaboradores quebrava (erro 500) quando havia
  candidato sem e-mail — efeito colateral do convite sem e-mail da 1.3.

## [1.6.0] — 2026-07-15

### Adicionado
- **Papel timbrado da empresa em todos os PDFs**: fichas, ofícios e manifesto
  usam as artes oficiais (cabeçalho de canto + rodapé institucional extraídos
  do modelo Word); fotos de documentos recebidos (RG, CPF…) viram página A4
  timbrada com o nome do documento e a data de recebimento. PDFs emitidos por
  órgãos (CTPS, certidões) seguem intactos — não se altera documento de
  terceiro. Vias já assinadas não mudam (hash preservado).
- **OCR com IA (Mistral)**: chave configurável pelo painel (com teste de
  leitura), cadeia de qualidade camada de texto do PDF → Mistral OCR →
  Tesseract local; falha de qualquer degrau cai para o seguinte em silêncio.
  Telemetria registra apenas tipo, hash e tamanho — nunca o conteúdo; a chave
  não aparece em logs; o aviso de privacidade do candidato passou a mencionar
  a leitura assistida por IA. PDFs escaneados (sem camada de texto) agora
  também são lidos quando a IA está ativa.

## [1.5.0] — 2026-07-15

### Adicionado
- **Fichas e assinaturas visíveis no painel**: o detalhe do candidato mostra
  cada documento exigido com o estado (assinado/aguardando), alerta quando o
  formulário está incompleto (fichas sairiam vazias) e ganhou o botão
  **"Notificar pendências por e-mail"** — cobrança com a lista exata do que
  falta e link novo. Nasceu de incidente real: e-mail cadastrado depois, e a
  pessoa nunca soube que havia fichas para preencher e assinar.
- **Termo de Consentimento LGPD (credenciamento)** no kit INFRAERO: gerado e
  assinado junto com os demais documentos do posto, com o mesmo código único.
- Painel do RH com **sidebar esquerda retrátil**, **barra de atividade** e
  botões travados durante requisições (fim do clique repetido); frases de
  espera agora também no painel.
- **Flash (torch)** na câmera guiada, quando o aparelho suporta.
- Foto OU arquivo para **todos** os documentos (fim do atalho que mandava
  CTPS/PIS direto ao seletor).
- Responsividade do painel para celular e tablet (tabelas com rolagem
  própria, revisão empilhada, métricas em grade).
- README rico (dores → soluções, rollback, resumo em inglês), CHANGELOG
  completo e LICENSE MIT.

### Alterado
- Salvar e-mail no contato avisa explicitamente que **não** envia nada
  sozinho — a notificação é um ato separado e auditado.

## [1.4.0] — 2026-07-15

Três fases nascidas de 11 anotações de uso real em produção, priorizadas em
mesa-redonda com foco em auditoria, LGPD e integridade das assinaturas.

### Adicionado
- **Fase 1 — controle do candidato:** ver o próprio envio (PDF), excluir envio
  ainda não aprovado e reenviar; preview de conferência da foto antes do envio;
  aviso de ciência do cartão de mobilidade (GO) com carimbo de data imutável;
  contrato do posto exibido a partir do cadastro (nada digitado à mão).
- **Fase 2 — poderes manuais do RH:** inserção de documento recebido fora do
  sistema (WhatsApp/e-mail/presencial) com etiqueta de origem; reabertura de
  status com motivo obrigatório; correção de dados da ficha por seção com
  auditoria campo a campo (antes → depois) e **re-assinatura granular** — só os
  documentos onde o dado aparece são invalidados e voltam para o candidato.
- **Fase 3 — frente e verso:** envio multi-arquivo vira um único PDF por
  documento; câmera guiada captura frente e verso em sequência (com passo
  opcional); OCR lê o texto combinado das partes.
- Assinaturas invalidadas são historizadas (nunca apagadas): o verificador
  público responde "assinatura substituída" com data e hash da via antiga; cada
  via assinada tem arquivo próprio no storage.
- E-mail/celular do candidato editáveis pelo RH e pelo próprio candidato, com
  trilha antes → depois na auditoria.
- Painel do RH com **sidebar esquerda retrátil**, barra de atividade global e
  botões travados durante requisições (fim do clique repetido).
- Captura por **foto OU arquivo para todos os documentos** (inclusive CTPS/PIS
  digitais — há quem tenha o cartão físico na mão).

### Alterado
- Comprovante de escolaridade passou a ser opcional.
- Câmera guiada sem disparo automático: o botão habilita quando o quadro está
  bom, mas quem fotografa é a pessoa; medidas de luz/foco restritas à moldura,
  com detecção de presença do documento.
- Exclusão/rejeição/substituição de arquivo varre todos os arquivos do slot
  (frente, verso, PDF) — cada um com hash SHA-256 na auditoria antes de sair.

### Corrigido
- Câmera dizia "tudo certo" com o documento fora do enquadramento (as medidas
  eram da cena inteira, não da moldura).

## [1.3.0] — 2026-07-15

### Adicionado
- Convite sem e-mail (só o nome é obrigatório): link em destaque para copiar e
  mandar pelo WhatsApp; e-mail vira pendência da ficha (o código de assinatura
  chega por ele).
- Leitor de identidade aceita **RG ou CNH**: detecta qual é, guarda no slot
  certo e avisa com gentileza quando a CNH veio no lugar do RG.
- OCR estendido: CNH (registro/categoria), título de eleitor (número/zona/
  seção), documento de CPF e CEP de comprovante de endereço; sugestões
  aplicadas **só com consentimento explícito** e nunca sobre campos preenchidos.
- Recusa imediata de documento de CPF com número divergente da ficha.
- **Câmera guiada** com moldura por tipo de documento, dicas em tempo real de
  luz/foco/enquadramento e conferência da foto; leitores junto aos campos que
  preenchem (RG/CNH na etapa de dados, comprovante na etapa de endereço, com
  moldura focada no cabeçalho da conta).
- Olhinho (mostrar/ocultar) em todos os campos de senha e segredos.
- Tema claro/escuro seguindo o dispositivo, com troca manual.
- Testes Playwright no CI contra a stack completa, incluindo a câmera (fake
  device do Chromium).

## [1.2.0] — 2026-07-14/15

### Adicionado
- Validações inteligentes no upload: foto tremida/borrada recusada na hora
  (variância do Laplaciano) e comprovante de endereço com mais de 90 dias
  bloqueado com mensagem clara.
- **Manifesto de assinatura** gravado como última página de cada PDF assinado:
  hash SHA-256, ID do registro, assinante, datas (Brasília + UTC), IP real,
  dispositivo, método e modalidade legal — com QR code para o **verificador
  público** (`/verificar/<id>`), que exibe dados minimizados (LGPD).
- Portal único de retorno **/entrar**: CPF + 2 perguntas de verificação
  derivadas da própria ficha (estilo TSE), com anti-enumeração, lockout e
  fallback de link por e-mail.
- Relatório de colaboradores com filtros e exportação **Excel** (~49 colunas).
- **Postos de serviço** com documentos específicos por contrato (ex.: ofícios
  INFRAERO) gerados em PDF fiel ao layout oficial e assinados na plataforma;
  assinantes dos documentos editáveis pelo painel.
- Nome social (Decreto 8.727/2016) e filiação (pai omitível) na ficha e nos
  documentos.
- Repaginada visual "fintech": fonte própria, cores vibrantes, micro-animações
  (com respeito a `prefers-reduced-motion`); máscara de datas `dd/mm/aaaa`
  digitável (o público trava no date picker).
- Botão "copiar link" por candidato no painel (para WhatsApp, sem reenviar
  e-mail).

## [1.1.0] — 2026-07-14

Primeira versão em produção (VPS via Portainer) + melhorias da v1.1.

### Adicionado
- Validação de CPF com dígito verificador (algoritmo da Receita) no backend e no
  formulário (aviso imediato + máscara), para titular e dependentes.
- Dashboard de métricas no painel do RH: candidatos, em andamento, documentos
  aguardando revisão, reenvios pendentes, dossiês gerados e tempo médio até o dossiê.
- "Esqueci minha senha" na tela de login: link por e-mail válido por 30 minutos e de
  uso único.
- Gestão da equipe do RH pelo painel: criar usuários (com e-mail de boas-vindas),
  editar, redefinir senha e ativar/desativar (com proteções contra auto-bloqueio).
- Envio de e-mail com "Fazer login com o Google" (OAuth + Gmail API), além do
  Microsoft 365; prioridade M365 → Google → SMTP.
- Teste de SMTP com diagnóstico dirigido (mostra a resposta exata do servidor e o
  passo de correção para os casos comuns do Microsoft 365).

### Corrigido
- Página em branco ao abrir um candidato no painel (hook condicional no React).
- Aprovar/rejeitar em massa não funcionavam (ordem de rotas no FastAPI); erros das
  ações em massa agora sempre aparecem na tela.
- Links gerados (link mágico, reset, e-mails, callback OAuth) agora derivam do endereço
  público da própria requisição — funcionam em localhost, IP:porta e domínio sem
  configurar BASE_URL; nginx preserva a porta.

## [1.0.0-rc.1] — 2026-07-14

Primeira versão candidata do Portal de Admissão.

### Adicionado
- Portal do candidato (mobile-first, sem senha): link mágico, aceite LGPD, wizard de 6
  etapas com autosave por campo, ViaCEP, dependentes ilimitados, tour guiado e tooltips
  com dicas por documento.
- Assinatura eletrônica simples (Lei 14.063/2020): código único por e-mail assina as 3
  fichas de uma vez; vias assinadas enviadas em anexo; trilha de evidências (hash, IP,
  user-agent, instante).
- Fichas Cadastral, de Emergência e Termo de VT geradas em PDF fiéis aos templates
  oficiais (textos legais, declarações, identificador de resposta).
- Checklist de documentos com regras condicionais (reservista, PCD, casamento,
  dependentes por idade, cartão VT), upload com normalização foto/Word→PDF e feedback
  imediato; botão "Concluí meu envio".
- Painel do RH: convites, revisão com visualizador de PDF, aprovação/rejeição individual
  e em massa (e-mail agrupado), dossiê único em A4 padronizado na ordem oficial (com opção
  de dossiê parcial), configurações (perfil, senha, SMTP com teste, Microsoft 365 via
  OAuth/Graph), auditoria.
- Infra: PostgreSQL + migrations Alembic automáticas no start (atualização sem perda de
  dados), MinIO com expurgo LGPD diário, Redis/RQ, e-mails HTML modernos, telemetria de
  requisições e trilha de auditoria.
- Deploy: compose base+variantes (ip / traefik / certbot), stack única para Portainer com
  imagens do GHCR publicadas por CI (GitHub Actions).

[1.7.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.7.0
[1.6.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.6.0
[1.5.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.5.0
[1.4.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.4.0
[1.3.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.3.0
[1.2.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.2.0
[1.1.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.1.0
[1.0.0-rc.1]: https://github.com/fontesmidias/admissao/releases/tag/v1.0.0-rc.1
