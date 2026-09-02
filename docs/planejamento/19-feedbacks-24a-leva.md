# 19 — 24ª leva de feedbacks (02/09/2026)

> **Origem.** Brain dump de 15 itens do Bruno após uso em produção (v3.16.1),
> mais o layout novo do Tirvu (item 16), trazido no mesmo dia.
>
> **Este documento é o rastro que o item 14 pediu** — *"documente, pois ultimamente
> eu tenho pedido várias coisas, você não conclui e fica por isso mesmo"*. Ele
> responde, a qualquer momento, o que foi pedido, o que já foi decidido e o que
> segue aberto, sem depender de reler uma conversa.
>
> **Produzido com `bmad-spec`**, validado por preservação (nenhum item perdido).
> A área de trabalho do BMad fica em `_bmad-output/specs/spec-feedbacks-24a-leva/`
> (não versionada); **este arquivo é a cópia canônica versionada**. Ao atualizar,
> re-derivar lá e republicar aqui.

---


> **Contrato canônico.** Este documento é o contrato completo e validado por preservação do que construir, testar e validar. Ele é derivado do `.memlog.md` da área de trabalho — os anexos ao final fazem parte do contrato.

# 24ª leva de feedbacks — Portal de RH Green House

## Why

Uma **dor de operação** relatada pelo Bruno depois de usar o sistema em produção (v3.16.1). São 15 itens que vão de um caractere invisível no tema escuro a três módulos que ainda não existem — e um deles, o item 14, não é pedido de funcionalidade: é a constatação de que *"ultimamente eu tenho pedido várias coisas, você não conclui e fica por isso mesmo"*. Esse item é a razão de este SPEC existir antes de qualquer código: sem rastro persistente, uma leva deste tamanho perde itens por esquecimento, não por decisão.

Dois itens carregam risco que excede o tamanho do código. O **item 5** (conta salário) pode fazer um admitido acreditar que receberá no banco que ele informou, quando não é isso que acontece — expectativa errada sobre salário, criada por um texto. O **item 13** produz planilha de folha **errada em silêncio**: o RH filtra por posto, exporta, e o arquivo traz gente de fora do filtro, sem nada denunciando.

## Capabilities

- **CAP-1** — *(item 6)*
  - **intent:** O "?" de ajuda do portal do candidato é legível no tema escuro.
  - **success:** Contraste do glifo contra o próprio fundo ≥ 4,5:1 medido no tema escuro, nas telas do wizard e do checklist.

- **CAP-2** — *(item 13)*
  - **intent:** Exportar entrega exatamente quem está marcado; sem ninguém marcado, entrega o que está filtrado na tela.
  - **success:** Marcar N linhas e exportar produz planilha com **essas N pessoas**, ignorando os filtros do topo. Sem marcação, a planilha traz exatamente quem a tela mostra. Exportar é ação em massa, ao lado de efetivar e desligar — não um botão de cabeçalho que desconhece a seleção.

- **CAP-2b** — *(item 13)*
  - **intent:** Ninguém desaparece da planilha sem a tela dizer.
  - **success:** Se alguém visível na tela filtrada não entra no arquivo — por ser importado do Tirvu, por não ser colaborador, ou por qualquer outra regra —, a tela **nomeia quem ficou de fora e por quê**, antes de baixar.

- **CAP-3** — *(item 13b)*
  - **intent:** A tela de Admissões/candidatos oferece exportação com o mesmo contrato de CAP-2, e o controle fica onde se procura por ele.
  - **success:** O RH marca candidatos em Admissões e exporta, sem passar por Colaboradores. O controle está junto das demais ações em massa.

- **CAP-4** — *(item 3)*
  - **intent:** O RH **exclui** candidato antigo ou duplicado, com motivo obrigatório, pela lixeira. *(Decidido: excluir, não fundir.)*
  - **success:** Excluir remove o registro das telas, grava o motivo na auditoria, e o item aparece na lixeira **e volta de lá** — restauração testada, não presumida.

- **CAP-5** — *(item 9)*
  - **intent:** O RH gera a autodeclaração de residência a partir da página do candidato/colaborador.
  - **success:** Um clique na ficha produz o documento; hoje ele só nasce pelo wizard quando o comprovante é de terceiro.

- **CAP-6** — *(item 1)*
  - **intent:** A página de assinatura de documentos abre sem carregar tudo de uma vez.
  - **success:** Tempo até a primeira tela útil medido antes e depois, com queda demonstrável na base real — não em banco de teste com poucos registros.

- **CAP-7** — *(item 2)*
  - **intent:** Quem sai do link e volta depois cai na **etapa pendente** do fluxo — o sistema decide sozinho qual é.
  - **success:** Falta documento leva ao checklist; falta assinar leva à assinatura. A pessoa nunca abre uma tela que não tem o que fazer.

- **CAP-8** — *(item 4)*
  - **intent:** No módulo de assinaturas, quem assina vê o documento antes de assinar (conferência) e vê o que já assinou.
  - **success:** A tela responde sem sair dela: *o que preciso conferir?* e *o que eu já assinei?*.

- **CAP-8b** — *(item 4, confirmado por investigação)*
  - **intent:** Quando a assinatura se conclui, o documento é disparado a uma **lista de destinatários configurável por tipo de documento**, e a tela diz para quem foi.
  - **success:** Concluir um roteiro (o requerimento do creche é o caso do Bruno) faz o documento chegar aos destinatários configurados no painel, e a ficha registra para quem seguiu e quando. **Hoje não é disparado a ninguém** — `avancar_solicitacao` devolve lista de notificação **vazia** ao concluir. O mesmo mecanismo serve CAP-19 (termo de VT → colaborador + RH + DP) e CAP-21.

- **CAP-9** — *(item 4b)*
  - **intent:** Os documentos assinados no reembolso-creche após a ativação aparecem no módulo do creche e na página do candidato/colaborador.
  - **success:** Um benefício ativo com requerimento assinado mostra esse documento nos três lugares; hoje não aparece em nenhum.

- **CAP-10** — *(item 5)*
  - **intent:** O banco da conta salário é atributo do posto — com padrão da casa, customização por posto e cadastro de bancos novos — e consta na ficha de integração e no ato de admissão.
  - **success:** Trocar o banco de um posto muda o que sai nos documentos daquele posto, sem tocar nos demais e sem alterar documento já assinado.

- **CAP-11** — *(item 5)*
  - **intent:** O texto sobre conta salário informa a pessoa sem desmotivá-la a fornecer os próprios dados bancários.
  - **success:** Redação validada pelo Bruno antes de virar texto de documento assinável. Ver `voz-editorial-conta-salario.md`.

- **CAP-12** — *(item 8)*
  - **intent:** O Termo de Opção do VT declara o prazo de pagamento do VT inicial, customizável pelo RH.
  - **success:** O RH altera o prazo pelo painel e o termo emitido a seguir traz o novo valor, sem deploy.

- **CAP-13** — *(item 8)*
  - **intent:** A ficha de integração traz as mesmas datas e prazos de VT e VA do termo, lidas da mesma fonte.
  - **success:** Alterar o prazo num lugar muda nos dois; divergência entre termo e ficha é impossível por construção.

- **CAP-14** — *(item 8)*
  - **intent:** O RH acrescenta informações próprias ao bloco de integração pelo front.
  - **success:** Texto novo aparece na ficha emitida a seguir, sem deploy.

- **CAP-15** — *(item 12)*
  - **intent:** O cadastro público do Banco de Talentos coleta RG (número + órgão/UF expedidor), filiação e CPF, visíveis ao RH no painel.
  - **success:** Os campos são preenchíveis no cadastro público e aparecem na ficha do talento.

- **CAP-16** — *(item 12)*
  - **intent:** O RH decide pelo front quais campos do Banco de Talentos são obrigatórios.
  - **success:** Tornar um campo opcional pelo painel faz o cadastro público aceitá-lo vazio, sem deploy.

- **CAP-17** — *(item 12)*
  - **intent:** O RH faz CRUD dos cargos oferecidos no Banco de Talentos.
  - **success:** Cargo criado pelo painel aparece na lista do cadastro público; hoje a lista está chumbada no código.

- **CAP-18** — *(item 7)*
  - **intent:** O assistente conectado por MCP alcança o conjunto de tarefas que o papel do usuário permite, e o catálogo orienta o uso.
  - **success:** Trocar o papel no painel muda o que o assistente consegue fazer; e um pedido em linguagem natural típica do RH chega à ferramenta certa. Hoje são 5 ferramentas fixas e o papel não altera nada.

- **CAP-19** — *(item 10)*
  - **intent:** Módulo Termo de Opção de VT: link público de adesão/atualização que pré-preenche quem já está na base, coleta de quem não está, coleta a assinatura, compõe a documentação do colaborador e distribui o termo assinado para colaborador, RH e DP com destinatários customizáveis.
  - **success:** Uma pessoa completa o fluxo pelo link e o termo assinado chega aos três destinos configurados.

- **CAP-20** — *(item 11)*
  - **intent:** Módulo de movimentação/atualização funcional do colaborador, substituindo o Microsoft Forms que o RH preenche hoje.
  - **success:** Uma movimentação é registrada pelo sistema, com trilha de quem pediu e quem aprovou, sem passar pelo Forms.

- **CAP-21** — *(item 15)*
  - **intent:** Módulo de geração de certificados.
  - **success:** A definir com o Bruno — ele pediu explicitamente para *"elaborar isso juntos"*. Ver `modulos-novos.md`.

- **CAP-22** — *(item 14)*
  - **intent:** Existe rastro persistente e consultável do que foi pedido, do que foi entregue e do que segue aberto.
  - **success:** A qualquer momento é possível responder "o que da 24ª leva ainda está aberto?" sem reler a conversa.

- **CAP-23** — *(item 16, trazido em 02/09/2026)*
  - **intent:** O export para o Tirvu usa o layout novo de 34 colunas, preenchendo as 6 opcionais a partir do que o sistema já coleta.
  - **success:** A planilha sai com as 34 colunas na ordem do modelo do fornecedor; Nome do Pai, Nome da Mãe, Nº Cartão DF Trans, Nº do RG, Órgão Expedidor e Data de Emissão vêm preenchidos para quem tem o dado, e vazios — **sem virar pendência** — para quem não tem. O Nº Cartão DF Trans sai como **texto**, preservando zero à esquerda.

## Constraints

- **Repositório é PÚBLICO** — nenhum dado real (CPF, e-mail, nome de colaborador) em código ou artefato versionado.
- **Documento assinado nunca muda** — o hash do ato é calculado sobre o PDF; mudança de texto ou layout vale só para documentos futuros. Isso rege CAP-10, CAP-11, CAP-12 e CAP-13.
- **Ação em lote que envia e-mail é trabalho de fila**, nunca de request — o nginx corta em 60s, e o resultado seria "erro de rede" com metade dos e-mails enviados. Rege CAP-19.
- **Toda rota sob `/rh/` declara permissão** via `Depends(exige(...))`; rota sem permissão reprova no CI.
- **E-mail novo nasce no catálogo** de `email_templates.py`; **documento novo nasce** em `documentos_catalogo.py`; **texto editável** mora em `textos_documentos.py`.
- **Exclusão passa pela lixeira E entra no mapa `classes_restauraveis`** — senão a lixeira vira via de mão única. Rege CAP-4.
- **Prazo e data de documento não se chumbam em código** quando o RH pode alterá-los — rege CAP-12, CAP-13, CAP-14.
- **Nº Cartão DF Trans é TEXTO na planilha, nunca número** — como número o Excel come o zero à esquerda e o cartão entra errado na integração (orientação do fornecedor). Rege CAP-23.
- **As 6 colunas novas do Tirvu são opcionais e o layout de 28 colunas continua aceito** — campo vazio não vira pendência bloqueante. Rege CAP-23.

## Non-goals

- **Não integrar com o Microsoft Forms.** Os formulários dos itens 10 e 11 servem de fonte de campos; o destino é substituí-los, não conversar com eles.
- **Não migrar dado histórico** de banco/conta salário, prazos de VT/VA ou cargos de talento já gravados. Valor antigo mantém o significado antigo.
- **Não reescrever o módulo de assinaturas.** O item 4 pede revisão de visibilidade e de fluxo, não refundação — o multi-signatário, a assinatura por OTP e o manifesto continuam como estão.
- **Não alargar o papel do MCP para resolver CAP-18.** A ferramenta cabe no papel; o papel não cresce para caber na ferramenta.
- **Não entregar as cinco ondas de uma vez.** Registrar tudo é obrigatório; entregar tudo junto não é.

## Success signal

O Bruno abre o sistema depois da Onda 1 e as três coisas que ele não conseguia fazer — ver a interrogação no escuro, exportar exatamente quem filtrou, apagar o candidato duplicado — funcionam. E, meses depois, qualquer pessoa consegue responder o que da 24ª leva ficou aberto sem reler uma conversa: é o item 14 deixando de se repetir.

## Assumptions

- Item 15 trata de certificados de treinamento/participação emitidos pelo RH, por analogia com o módulo de certificações/brigada já existente.
- Os Microsoft Forms dos itens 10 e 11 são fonte de campos, não sistema a integrar.
- "Revisar esse módulo" (item 4) significa fechar as lacunas de visibilidade nomeadas, não reconstruir o módulo.

## Decidido pelo Bruno (02/09/2026)

- **Item 2 → CAP-7:** ao voltar pelo link, cair na **etapa pendente** do fluxo; o sistema decide sozinho.
- **Item 3 → CAP-4:** **excluir** pela lixeira, não fundir.
- **Item 13 → CAP-2:** exportar entrega **exatamente quem está marcado**; sem marcação, o que está filtrado na tela.
- **Item 4 → CAP-8:** investigar no código antes de estimar. **Feito** — resultado abaixo.

## Achado por investigação (02/09/2026)

**O disparo pós-assinatura não existe.** `roteiro_assinatura.py::avancar_solicitacao` (linhas 115-117) devolve `"notificar": []` quando a solicitação **conclui** — ele só notifica quem é a *próxima* etapa da fila; ao terminar, não há ninguém a avisar. Os quatro chamadores repassam essa lista vazia.

Confirma o caso que o Bruno citou: no requerimento do creche (`creche_publico.py:939`) a rota devolve apenas `{"assinado": true, "concluido": ...}` e **não envia nada a ninguém**.

Logo o item 4 são **dois trabalhos** (CAP-8 e CAP-8b), não um.

## Open Questions

- **Item 5:** o banco da conta salário é um por posto ou vários? Quem define o padrão da casa quando o posto não diz nada?
- **Item 8:** os "5 dias úteis" contam a partir de qual marco — data de contratação, fim do ciclo de pagamento, ou assinatura do termo?
- **Item 10:** o termo assinado por quem ainda não está na base cria registro novo, ou fica pendente até a pessoa existir?
- **Item 11:** quais movimentações o módulo cobre? Quem aprova cada uma?
- **Item 12:** RG, filiação e CPF no cadastro público ampliam o dado pessoal coletado de quem ainda não é candidato. Qual a base legal e a retenção?
- **Item 15:** certificado de quê? Quem assina? Precisa de verificação pública por QR?

*(As quatro últimas pertencem às Ondas 3 e 5 — não bloqueiam a Onda 1.)*
- **Item 8:** os "5 dias úteis" contam a partir de qual marco — data de contratação, fim do ciclo de pagamento, ou assinatura do termo?
- **Item 10:** o termo assinado por quem **ainda não está na base** cria registro novo, ou fica pendente até a pessoa existir?
- **Item 11:** quais movimentações o módulo cobre (promoção, mudança de posto, de jornada, reajuste, desligamento)? Quem aprova cada uma?
- **Item 12:** RG, filiação e CPF no cadastro **público** ampliam o dado pessoal coletado de quem ainda não é candidato. Qual a base legal e a retenção? O expurgo hoje mira admissão.
- **Item 15:** certificado de quê? Quem assina? Precisa de verificação pública por QR, como os documentos assinados já têm?



---

# Anexo — Priorização — ganho × esforço

O Bruno pediu: *"dentro das prioridades de maior ganho e menor esforço, mas que nenhuma fique de fora"*. As duas metades da frase têm pesos diferentes — **nenhuma fica de fora** é obrigação; **a ordem** é otimização. Por isso a priorização vira **ordem de ondas**, não corte de escopo.

### Como a ordem foi decidida

Três critérios, nesta precedência:

1. **Falha silenciosa vem antes de falha visível.** Um defeito que o RH não tem como perceber sozinho é mais caro que um que incomoda todo dia — porque o segundo será relatado e o primeiro não.
2. **Esforço medido no código, não estimado no olho.** Vários itens que parecem grandes já têm metade da infraestrutura pronta; outros que parecem pequenos não têm rota nenhuma. Ver `achados-no-codigo.md`.
3. **Risco de negócio quebra empate.** Item que cria expectativa errada sobre salário ou move dado funcional sobe, mesmo sendo pequeno em linhas.

### As ondas

#### Onda 1 — ganho imediato, esforço baixo

| Cap | Item | Por que aqui |
|---|---|---|
| **CAP-2 / CAP-2b** | 13 | **Falha silenciosa.** Marca as pessoas, exporta, vêm outras — e a planilha vai para a folha. O backend já aceita `ids`; falta exportar virar ação em massa. Esforço baixo, risco alto — primeira da fila |
| **CAP-1** | 6 | Uma linha de CSS. Contraste medido, defeito conhecido (`--tinta` invertendo no escuro) |
| **CAP-5** | 9 | O gerador da autodeclaração **já existe**; falta o botão na ficha |
| **CAP-4** | 3 | Bloqueia o Bruno hoje. Decidido: excluir pela lixeira. Exige rota nova + lixeira + mapa de restauração — caminho conhecido |
| **CAP-3** | 13b | Reusa o contrato que CAP-2 acabou de estabelecer; fazer junto é mais barato que depois |
| **CAP-7** | 2 | Decidido (cair na etapa pendente). Sai da Onda 2 e vem para cá, porque a decisão já foi tomada |
| **CAP-23** | 16 | Layout novo do Tirvu. **Os 6 campos já são coletados** — é ligar, não coletar. Anda junto com CAP-2/2b porque mexe no mesmo export, e a regra "só quem não existe no Tirvu" explica o "faltou gente" do item 13 |

**Por que esta onda primeiro:** seis itens que o Bruno sente no mesmo dia, todos já decididos — nenhum espera resposta dele para começar.

#### Onda 2 — módulo de assinaturas e creche

| Cap | Item | Observação |
|---|---|---|
| **CAP-9** | 4b | Documento assinado que não aparece em lugar nenhum. Mesma família do defeito da v3.16 |
| **CAP-8** | 4 | O maior dos três — **investigar primeiro** se o disparo pós-assinatura já acontece; a resposta decide se são um ou dois trabalhos |
| **CAP-6** | 1 | Performance; medir antes de otimizar, na base real |

**Nota:** CAP-7 subiu para a Onda 1 (decisão tomada). CAP-8 começa por investigação no código, não por implementação.

#### Onda 3 — VT, integração e Banco de Talentos configuráveis

| Cap | Item | Observação |
|---|---|---|
| **CAP-10/11** | 5 | **Maior risco de negócio da leva.** CAP-11 é redação, não código — ver `voz-editorial-conta-salario.md` |
| **CAP-12/13/14** | 8 | Fonte única de prazos; a infraestrutura de texto editável já existe |
| **CAP-15/16/17** | 12 | CAP-17 (CRUD de cargos) é o mais barato dos três e destrava o Bruno sozinho |

#### Onda 4 — MCP utilizável

| Cap | Item | Observação |
|---|---|---|
| **CAP-18** | 7 | Não é bug: são ferramentas que nunca foram escritas. Cada uma é um incremento — a onda pode parar a qualquer momento com valor entregue |

#### Onda 5 — módulos novos

| Cap | Item | Observação |
|---|---|---|
| **CAP-19** | 10 | O mais definido dos três; o Bruno vai fornecer o formulário |
| **CAP-20** | 11 | Precisa saber quais movimentações e quem aprova |
| **CAP-21** | 15 | Sem forma ainda — o Bruno pediu para elaborar junto |

#### Transversal

**CAP-22** (item 14) começa **agora**, com este SPEC, e continua no sprint plan. Não é uma onda; é a condição para as outras não se perderem.

### O que esta ordem não é

Não é ordem de importância. O item 11 (movimentação funcional) é provavelmente o de maior valor estrutural da leva inteira — e está na Onda 5 porque ainda não se sabe o que ele cobre. Ordem por ganho/esforço coloca o barato e certo antes do valioso e indefinido; isso é deliberado, e reversível assim que as perguntas forem respondidas.



---

# Anexo — Achados no código

Cinco dos quinze itens foram rastreados até a linha durante a distilação do SPEC. Isso muda estimativa: dois itens que pareciam grandes são pequenos, e um que parecia configuração é capacidade inexistente. Registrado aqui para que a implementação não redescubra.

### Item 6 — o "?" invisível no tema escuro

**Causa exata.** `frontend/src/styles.css:609`:

```css
.btn-ajuda {
  background: var(--tinta); color: #fff; ...
}
```

No tema escuro (`styles.css:113`) `--tinta` inverte para `#e9f4ec` — quase branco. O resultado é **"?" branco sobre círculo branco**, exatamente o que o Bruno descreveu.

É a armadilha da v2.46 (*token que inverte com o tema*) numa classe nova. O `.ajuda-q` do painel do RH **já foi corrigido** e traz o comentário explicando; o `.btn-ajuda` do portal do candidato ficou para trás.

**Alcance:** `CandidatoApp.jsx:142`, `Checklist.jsx:365`, `Wizard.jsx:217` — as três telas do portal do candidato.

**Esforço:** uma linha. Contraste tem de ser **medido** no navegador, não estimado.

### Item 13 — a exportação que ignora quem você marcou

> ⚠️ **Meu primeiro diagnóstico deste item estava errado** e o Bruno reprovou. Eu tinha lido como "filtro de coluna sem equivalente server-side". Não é isso. O registro fica para não se repetir o erro: o defeito é de **onde o botão vive**, não de qual filtro ele traduz.

**O backend está certo.** `colaboradores.py::_colaboradores_para_tirvu` (linha 207) já aceita `ids` e `posto_id`, e `exportar_tirvu_massa` (linha 240) os repassa. A capacidade de exportar por seleção **existe no servidor e nunca foi usada**.

**O defeito é estrutural no front.** Há dois mundos separados em `Colaboradores.jsx`:

| | Onde vive | Enxerga a seleção? |
|---|---|---|
| Efetivar / desligar / reverter | `acoesMassa` (linha 381), **dentro** do `DashPlanilha` | **Sim** |
| Exportar Tirvu / Dexion / Excel | cabeçalho da tela (linhas 437-442), **fora** do `DashPlanilha` | **Não** |

O `DashPlanilha` mantém a seleção em `selec` (um `Set`, linha 43) e a entrega a quem é ação em massa. **Exportar nunca foi ação em massa** — é botão de cabeçalho, e monta seu conjunto sozinho a partir dos filtros do topo (linha 154).

Resultado exato do que o Bruno relatou: **marca as pessoas, exporta, e vêm outras.**

**Três defeitos, não um** (confirmados com o Bruno):

- **(a) Marquei pessoas e exportou outras** — a seleção não chega ao botão.
- **(b) Não achei onde selecionar/exportar** — em Admissões não existe export em massa nenhum (só Colaboradores tem).
- **(c) Faltou gente que deveria estar** — alguém visível na tela não entrou no arquivo.

**Sobre (c) — hipótese a medir, não a afirmar:** `_colaboradores_para_tirvu` exclui `origem == "importacao"` por padrão (`incluir_importados=False`) e filtra `so_colaboradores=True`. Quem veio importado do Tirvu **some da planilha sem a tela dizer**. Confirmar na implementação antes de tratar como causa — e, seja qual for a regra, ela precisa **nomear quem ficou de fora** (CAP-2b).

**Comportamento decidido pelo Bruno:** exportar entrega **exatamente quem está marcado**; sem ninguém marcado, o que está filtrado na tela.

**Esforço:** baixo-médio. Mover exportar para `acoesMassa` e passar os `ids` que o backend já aceita.

### Item 13b — Admissões não exporta

Confirmado: exportação em massa existe só em Colaboradores (Tirvu e Dexion). A tela de Admissões não tem nenhuma. O Bruno notou — *"isso nem tem opção no módulo candidatos"* — e marcou "não achei onde selecionar/exportar" entre os sintomas.

### Item 3 — excluir candidato duplicado

**Não é permissão mal configurada.** Não existe rota `DELETE` de candidato em `app/api/candidatos.py` — a única é de teste-vinculado (linha 320). A capacidade **nunca foi construída**.

**Consequência para a implementação:** rota nova + permissão declarada + `mandar_para_lixeira` + entrada no mapa `classes_restauraveis` de `lixeira.py`. Sem a última, a lixeira vira via de mão única — o defeito da v2.72.2, que ocorreu em seis de oito entidades.

### Item 7 — o MCP com 5 ferramentas

`mcp/portal_rh_mcp/servidor.py` expõe exatamente cinco:

| Ferramenta | Natureza |
|---|---|
| `buscar_candidato` | leitura |
| `diagnostico_candidato` | leitura |
| `listar_admissoes` | leitura |
| `pendencias_tirvu` | leitura |
| `cadastrar_talento` | escrita |

Isso explica o relato *"já troquei as permissões dentro do sistema, mas não consigo pedir mais coisas"*: **trocar o papel não muda nada**, porque o teto não é a permissão — é o catálogo do servidor. A permissão já existe para ações que não têm ferramenta.

**Consequência:** CAP-18 não é correção de configuração; é escrever as ferramentas que faltam, uma a uma, cada uma cabendo na permissão do papel (nunca o contrário). E a segunda metade da queixa — *"não está intuitivo"* — é trabalho de **descrição de ferramenta**: é a descrição que faz o modelo escolher certo.

### Item 16 — layout novo do Tirvu (34 colunas)

Trazido pelo Bruno em 02/09/2026, com o arquivo `docs/Layout de Importação de Admissões (1).xlsx`.

**O que o modelo traz:** aba `Plan1`, **34 colunas**, uma linha só (cabeçalho, sem exemplo — a mesma armadilha da v2.83: valida a **forma**, não o **conteúdo**).

**As 28 primeiras batem exatamente** com o `COLUNAS_TIRVU` atual, na mesma ordem. As 6 novas são `AC`→`AH`:

| Col | Cabeçalho | O sistema já tem? |
|---|---|---|
| AC | Nome do Pai | ✅ `ficha.py:87` `nome_pai` |
| AD | Nome da Mãe | ✅ `ficha.py:86` `nome_mae` |
| AE | Nº Cartão DF Trans | ✅ `ficha.py:204` `cartao_dftrans` |
| AF | Nº do RG | ✅ `ficha.py:141` `rg_numero` |
| AG | Órgão Expedidor do RG | ✅ `ficha.py:142` `rg_orgao_emissor` |
| AH | Data de Emissão do RG | ✅ `ficha.py:143` `rg_data_expedicao` |

**Os seis já são coletados.** Nenhum campo novo a perguntar, nenhuma migration de coleta: o trabalho é **ligar** o que já existe às colunas novas. O `cartao_dftrans` inclusive já é usado no termo de VT (`fichas.py:567`) e no export de planilha (`export_planilha.py:117`).

**Três regras do fornecedor que viram teste:**

1. **DF Trans é TEXTO.** Como número, o Excel come o zero à esquerda e o cartão entra errado. O `montar_workbook_tirvu` já escreve célula a célula — garantir o tipo nesta coluna e travar em teste.
2. **As 6 são opcionais; o layout de 28 continua aceito.** Campo vazio **não pode virar pendência** — o export não recusa quem não tem RG ou DF Trans.
3. **Só admissões que ainda não existem no Tirvu.** Quem já está cadastrado lá é ignorado na importação. Isso confirma a regra que o export já aplica (`incluir_importados=False`, excluindo `origem == "importacao"`) — mas ver **CAP-2b**: quem for excluído precisa ser **nomeado na tela**, senão é exatamente o sintoma (c) do item 13, "faltou gente que deveria estar".

**Ligação com o item 13:** a regra 3 é provavelmente a causa do (c). O comportamento está certo; o silêncio é que não está.

**Esforço:** baixo. Estender `COLUNAS_TIRVU` e o `linha_tirvu`, sem tocar em coleta.

### Item 9 — a autodeclaração

O gerador `gerar_autodeclaracao_residencia` já existe e é acionado pelo wizard quando o comprovante é de terceiro (`ficha.py::_sincronizar_autodeclaracao_residencia`). Falta **a porta na tela do RH** — é o padrão v3.16 (*ação que só existe dentro de outra ação não tem porta*).

**Esforço:** baixo, e já se sabe qual a recusa a evitar.



---

# Anexo — Voz editorial — conta salário

Companion de CAP-11. Trata do **texto**, não do código. É o item da leva com maior risco de negócio por linha escrita: ele decide o que um admitido acredita sobre onde vai receber o salário.

### O problema, nas palavras do Bruno

> *"não podemos desmotivá-los a não ser os dados bancários. Os dados bancários que ele oferece, são para fins de receber o primeiro salário lá no seu banco, caso não dê tempo de ativar a conta salário (aqui, não podemos dar essa intenção, seja estratégico nas palavras)"*

### A tensão real

Três verdades que precisam conviver no mesmo parágrafo:

1. O salário será pago em **conta salário**, num banco vinculado ao posto — não no banco que a pessoa escolher.
2. Os dados bancários que ela informa **têm uso real**: receber o primeiro salário, se a conta salário não estiver ativa a tempo.
3. Se o texto disser (1) com clareza demais e (2) de leve, a pessoa conclui que informar os dados é inútil e **não informa** — e aí o primeiro salário não tem para onde ir.

O risco não é a pessoa se decepcionar depois. É ela **não preencher o campo agora**.

### O que o texto precisa fazer

- **Pedir o dado com propósito nomeado.** "Para garantir o pagamento do seu primeiro salário" é motivo verdadeiro e suficiente. Campo sem motivo declarado é campo que se pula.
- **Mencionar a conta salário como algo que a empresa providencia**, não como algo que substitui o que a pessoa está informando. As duas coisas são etapas de uma sequência, não alternativas concorrentes.
- **Não prometer prazo que o RH não controla.** "Caso não dê tempo de ativar" é a realidade; virar promessa datada cria a segunda expectativa errada.
- **Não sugerir que informar é opcional.** Mesmo sendo verdade que o salário acabará indo para a conta salário.

### O que o texto não pode fazer

- **Não afirmar que o salário será pago no banco informado.** É a expectativa errada que o item existe para evitar.
- **Não usar linguagem de escolha** ("banco de sua preferência", "onde você quiser receber") — ela cria a impressão de que a decisão é da pessoa.
- **Não enterrar a informação sobre conta salário** em letra miúda ou em documento que só aparece depois. Se a pessoa descobre no primeiro pagamento, o texto falhou mesmo estando tecnicamente correto.
- **Não pedir desculpas nem justificar a política.** O documento informa; não negocia.

### Onde o texto aparece

O mesmo conteúdo, coerente, em três lugares — e é por isso que ele precisa de fonte única:

| Lugar | Papel do texto |
|---|---|
| **Coleta dos dados bancários** (wizard) | Pedir o dado, dizendo para que serve |
| **Ficha de integração** | Informar como o pagamento funciona, com o banco do posto nomeado |
| **Ato de admissão** | Registrar formalmente o mesmo fato |

Divergência entre os três é o defeito a evitar — é a mesma família do que a v2.19 pagou (corpo copiável divergindo do documento oficial e perdendo 6% do VT).

### Processo

**O texto vai ao Bruno antes de virar documento assinável.** Duas razões: ele conhece a reação da equipe a este assunto, e — pela regra da casa — **documento assinado nunca muda**. Um texto ruim que já foi assinado por alguém não se corrige; corrige-se só para os próximos.

Recomendação: acionar `bmad-agent-ux-designer` (Sally) para redigir as variantes, com o Bruno escolhendo entre duas ou três — comparar textos concretos é mais produtivo que discutir princípio.



---

# Anexo — Módulos novos

Três dos quinze itens não são ajustes: são módulos que não existem. Este companion registra o que o Bruno disse sobre cada um, o que já existe no sistema que pode ser reusado, e o que falta decidir antes de virarem histórias.

Os três estão na **Onda 5** por indefinição, não por baixo valor — o CAP-20 é provavelmente o de maior valor estrutural da leva.

---

### CAP-19 — Termo de Opção de VT (item 10)

O mais definido dos três. O Bruno descreveu o fluxo inteiro.

**Fluxo pedido:**

1. Link público, apresentado como *"atualização/adesão"*
2. Se a pessoa já é candidato/colaborador → **pré-preenche** os dados dela
3. Se não é → ela **informa** os dados pertinentes ao termo
4. Ela **assina**
5. O termo assinado **compõe a documentação do colaborador**
6. E é **distribuído**: colaborador + RH + **DP** (por e-mail, com destinatários **customizáveis**)

**O que já existe e deve ser reusado** — o Bruno indicou (*"já temos essa expertise por ocasião da admissão"*):

| Peça | Onde vive |
|---|---|
| Link público com identificação por CPF + 2FA | gate do creche / portal (`AcessoPortal`, `AcessoCreche`) |
| Coleta de dados pessoais e bancários | wizard de admissão |
| Assinatura com OTP + manifesto + hash | `api/assinaturas.py` |
| Distribuição por e-mail com destinatários configuráveis | matriz de `notificacoes.py` + catálogo de `email_templates.py` |
| Termo de VT como documento | `DocumentoAssinavel.termo_vt` |

**Restrições que já se sabem:**

- O envio para três destinos é **trabalho de fila**, não de request.
- O e-mail nasce no **catálogo**; os destinatários entram pela **matriz**, não em lista paralela.
- Link em e-mail corporativo é **pré-aberto por robô** (v2.28) — a ação que consome vai em `POST`, nunca em `GET`.
- O termo já assinado **não muda**.

**Falta decidir:** o que acontece quando quem assina **ainda não está na base** — cria registro novo ou fica pendente até a pessoa existir? *(Open Question no SPEC.)*

**Insumo esperado do Bruno:** o formulário do Microsoft Forms, como fonte dos campos.

---

### CAP-20 — Movimentação / atualização funcional (item 11)

> *"Hoje temos um Microsoft Forms, que o RH preenche, mas precisamos sistematizar isso para poder escalar"*

O item mais aberto e o de maior peso estrutural. Movimentação funcional altera **vínculo** — posto, cargo, jornada, salário — que é justamente o conjunto de campos que alimenta o export para a folha.

**Por que é delicado:** este módulo escreve nos campos que o Tirvu/Dexion consomem. Uma movimentação errada não dá erro; ela entra limpa e sai errada na folha meses depois — a assinatura do defeito do "Registra Ponto" (v1.82) e do CBO chumbado (v2.54).

**O que já existe:**

| Peça | Observação |
|---|---|
| `Candidato` com posto, cargo, jornada, situação | os campos que a movimentação altera |
| Reverter colaborador→candidato (v1.65) | precedente de mudança de vínculo **com motivo obrigatório e auditoria** |
| Troca de matrícula com histórico (v2.45) | precedente de alteração que **preserva o valor anterior** |
| Lixeira e auditoria | trilha de quem fez e por quê |

**Falta decidir** *(Open Question no SPEC)*: quais movimentações o módulo cobre — promoção, mudança de posto, de jornada, reajuste, desligamento — e **quem aprova cada uma** antes de valer. A resposta define se o módulo tem fluxo de aprovação ou é registro direto.

**Recomendação:** acionar `bmad-agent-pm` (John) antes de escrever história. O escopo aqui é decisão de produto, não de implementação.

---

### CAP-21 — Geração de certificados (item 15)

> *"ter um módulo de geração de certificados (elaborar isso juntos)"*

O Bruno pediu **explicitamente** para elaborar junto. Entra no SPEC como capacidade a especificar — registrar como escopo fechado seria inventar o que ele quer.

**O que já existe e provavelmente se aplica:**

| Peça | Observação |
|---|---|
| Certificações com validade e aviso de vencimento (v1.83) | já há o conceito de certificado com prazo |
| Brigada / certificação crítica de 24 meses | precedente de certificado por cargo |
| Geradores de PDF em papel timbrado | `fichas.py`, fpdf2 |
| Assinatura com verificação pública por QR | `api/assinaturas.py` |
| Catálogo de documentos com amostra e download | `documentos_catalogo.py` |

**Perguntas para a conversa** *(Open Questions no SPEC)*:

- Certificado **de quê** — treinamento, participação, brigada, tempo de serviço?
- **Quem assina** — a empresa, um responsável nomeado, ninguém?
- Precisa de **verificação pública por QR**, como os documentos assinados já têm?
- É **emitido em lote** (uma turma de treinamento) ou um a um? *(Se em lote e por e-mail: trabalho de fila.)*
- Entra no **dossiê**? — Atenção: o dossiê varre solicitações concluídas **sem filtrar origem**; documento novo entra nele por padrão, e o dossiê circula para o cliente (v2.67).

**Recomendação:** `bmad-party-mode` ou `bmad-brainstorming` com o Bruno. É o formato certo para algo que ainda não tem forma — e mais barato que especificar sozinho e refazer.
