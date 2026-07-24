# Central de Ajuda / Base de Conhecimento — análise (GitBook vs. alternativas)

> Pedido do Bruno: *"Estou pensando em usar o GitBook para criar uma Central de
> Ajuda/base de conhecimento. Tem custos? Quais os concorrentes e nuances? Quero
> algo prático, pois somente sou eu na equipe para fazer tudo."*
>
> Esta é **só a análise** — a decisão é sua. Preços verificados em jul/2026
> (fontes no fim); onde não confirmei, está dito.

## O que muda tudo na sua situação

Você é **uma pessoa só, de RH, não-desenvolvedora, sem tempo**. Isso reordena o
que importa: **o recurso mais escasso não é dinheiro de licença — é o seu
tempo.** Toda ferramenta "grátis" que exige montar pipeline, fazer deploy e
editar via Git é grátis em *licença* e cara em *tempo*. É a armadilha do
docs-as-code para o seu perfil.

Por isso, a pergunta certa não é "qual é a mais barata?", e sim **"qual me deixa
escrever e publicar sem virar administrador de sistema?"**

## Tabela rápida

| Ferramenta | Grátis? | Menor pago | Precisa programar? | Domínio próprio | Esforço p/ você |
|---|---|---|---|---|---|
| **Notion (Sites)** | Sim (publica na web de graça) | Plus US$10/membro/mês | Não | +US$8/mês | **Muito baixo** |
| **GitBook** | Sim (1 usuário, subdomínio, sem colaboração) | US$65/site/mês + US$12/editor | Não | Só no pago | Baixo |
| **Document360** | Limitado (50 artigos) | ~US$99/mês | Não | Sim | Baixo, mas caro |
| **Docusaurus** | 100% grátis | US$0 (+ deploy) | **Sim** (Node/Git) | Sim (grátis) | Médio/Alto |
| **MkDocs Material** | 100% grátis | US$0 (+ deploy) | **Sim** (Python/YAML) | Sim (grátis) | Médio (⚠️ ver nota) |
| **Confluence** | Sim (até 10 users) | ~US$5,42/user/mês | Não | Publicação pública fraca | Médio |
| **BookStack / Outline** | Grátis se auto-hospedar | US$0–10/mês | **Sim** (self-host) | Sim | **Alto** (você é o sysadmin) |
| **Zendesk / Help Scout** | Não (é helpdesk) | ~US$55/mês | Não | Sim | Baixo, mas overkill |

## Sobre o GitBook especificamente (o que você perguntou)

- **Tem plano grátis?** Sim, mas trava no essencial para uso real: só 1 usuário,
  só subdomínio `gitbook.io` (**sem domínio próprio**) e **sem convidar um 2º
  editor**. Serve para experimentar.
- **Quanto custa "pra valer"?** Domínio próprio + colaboração exigem o Premium:
  **US$65/site/mês + US$12 por editor** (cobrança anual). Leitores nunca pagam.
  Para uma central de RH pequena, na prática ~US$77/mês.
- **É bom para não-dev?** Sim — editor visual, sync opcional com o repositório
  (o "gancho" que te atraiu existe, mas não é obrigatório).
- **Veredito:** ótimo produto, mas **caro para o seu caso**. Você pagaria plano
  de time para publicar uma central que uma pessoa mantém.

## Recomendação prática (a de quem faz tudo sozinho)

**1ª opção — Notion Sites.** É a melhor relação *custo × esforço* para o seu
perfil:
- Publicar páginas na web é **gratuito** (inclusive no plano Free). Se você já
  usa Notion, é praticamente de graça.
- Editor visual, zero pipeline, zero deploy — você escreve e publica.
- Leitores (colaboradores) **não pagam nada**. Domínio próprio custa +US$8/mês
  se/quando quiser.
- Contra honesto: SEO e customização visual do site público são limitados. Para
  uma central de ajuda interna/semi-pública de RH, é aceitável.

**2ª opção — GitBook grátis para começar.** Se quiser a cara de "documentação de
produto" e topar o subdomínio `gitbook.io` no início, o plano free destrava o
piloto. Só saiba que domínio próprio e um 2º editor te empurram para os US$65/mês.

**Quando docs-as-code (Docusaurus) valeria a pena:** só se você decidir que vai,
de fato, escrever em Markdown e conviver com Git para publicar — aí o custo de
licença é zero e a documentação mora junto do código, versionada. Como você é RH
e sem tempo, **não recomendo começar por aqui**: cada correção de texto vira
commit, e a manutenção do build recai sobre você. (E há um sinal de alerta atual:
o *MkDocs Material* entrou em modo manutenção em nov/2025 — se fosse docs-as-code,
eu preferiria Docusaurus, mantido ativamente pela Meta.)

**O que eu evitaria no seu caso:** Document360 e Zendesk/Help Scout (caros e/ou
são helpdesk com KB acoplada — mais do que você precisa) e qualquer wiki
auto-hospedado (BookStack/Outline self-host) — transformam você em administrador
de servidor, exatamente o que "sou só eu na equipe" não comporta.

## Um caminho de custo quase zero, se topar

Se a ideia for **começar já e barato**: suba a central no **Notion**, organize
por seções (Admissão, Creche, Provas, Desempenho, Portal do colaborador…),
publique como site, e mais tarde — se sentir necessidade — avalie migrar para
GitBook/Docusaurus. Notion não te prende: exporta em Markdown, o que preserva a
porta de saída para docs-as-code no futuro, quando/se houver tempo (ou mão de
obra) para isso.

## Nuances verificadas / não confirmadas

- Preços do **Zendesk** e **Help Scout** vieram de fontes secundárias recentes,
  não da página oficial nesta rodada.
- **Confluence**: o ~US$5,42/user/mês é do produto como *wiki interno*; a
  publicação de **site público externo** historicamente depende de apps de
  terceiros e **não confirmei** número atual — por isso não o recomendo para
  portal público de colaboradores.

### Fontes de preço
GitBook: gitbook.com/pricing · Notion: notion.com/pricing e Notion Sites ·
Document360: document360 pricing · Help Scout: helpscout.com/pricing · Zendesk:
suite pricing · Confluence: atlassian pricing · Docusaurus: docusaurus.io/docs ·
MkDocs Material: squidfunk.github.io/mkdocs-material. (URLs completas no relatório
de pesquisa desta leva.)
