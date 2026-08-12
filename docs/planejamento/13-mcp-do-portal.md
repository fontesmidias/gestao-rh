# MCP do Portal — desenho, segurança e o que NÃO expor

> Status: **desenho aprovado, não implementado**. Decisões travadas com o Bruno
> em 2026-08-11 (party mode). Este documento é o contrato: quem for implementar
> segue daqui, e o que estiver em desacordo com isto é regressão, não melhoria.

## 1. O problema real, não o pedido literal

O pedido foi *"criar um MCP para o portal, tenho a Claude e gostaria que ela
automatizasse algumas coisas"*. Perguntado **qual tarefa manual irrita**, o Bruno
respondeu outra coisa — e a resposta é o projeto:

> *"cadastrar candidatos no banco de talento na mão. hoje eu tenho pouco mais de
> 14 mil currículos numa pasta chamada `vagas@` no meu Outlook profissional.
> está tudo lá, descentralizado. eu nem leio, mas sei que tem coisa boa lá e não
> está categorizado, não está arrumado, é uma bagunça."*

Isso não é uma tarefa chata. É **um ativo que a empresa já pagou para receber e
nunca leu**. O trabalho não é "ler e-mail": é transformar uma pasta do Outlook
num Banco de Talentos pesquisável.

Um segundo uso apareceu sozinho durante a análise do incidente do dossiê
(v2.93): se existisse uma ferramenta de **diagnóstico**, a analista teria
perguntado *"por que o dossiê do Luciano não gera?"* e recebido *"o PDF do nada
consta está corrompido"* — em vez de passar 54 minutos desmarcando exigências
médicas. As duas metades do MCP saem daí: **responder por quê** e **receber
talento**.

## 2. A decisão que mais importa: o MCP NÃO lê e-mail

Três caminhos foram considerados para chegar aos 14 mil currículos:

| Caminho | Por que foi descartado / escolhido |
|---|---|
| Servidor lê o Outlook via Graph | **Descartado.** Exige `Mail.Read` no tenant |
| Conta de serviço com pasta isolada | Alternativa viável, mas exige trabalho de tenant |
| **Quem já tem acesso lê; o MCP recebe** | **Escolhido** |

O escopo atual do sistema é `offline_access Mail.Send User.Read`
(`services/m365.py`). Ele **envia** e-mail; não lê. Passar a ler exigiria
acrescentar `Mail.Read` — e aí está o problema que decidiu a questão:

> **Não existe "só a pasta `vagas@`" no escopo do Graph.** O filtro de pasta é do
> nosso código; a *permissão* é da caixa inteira. `Mail.Read` numa caixa
> profissional de RH alcança contrato, jurídico, conversa com cliente e assunto
> de pessoal. `Mail.ReadBasic` não serve: lê metadado, e o currículo **é** o
> anexo.

Por isso: **quem lê o e-mail é quem já tem acesso legítimo a ele** (a Claude
operando no desktop do Bruno, na sessão dele). O MCP é a **outra ponta** — a
porta por onde o talento entra no portal, com validação, deduplicação e
auditoria. O servidor não ganha permissão nova sobre a caixa de e-mail de
ninguém.

## 3. A porta de escrita JÁ EXISTE — não criar outra

`POST /rh/talentos` (`api/talentos.py::cadastrar_pelo_rh`) nasceu na v2.73
justamente para o *"currículo que chega por e-mail"*, e já traz a defesa que este
projeto precisaria:

- **Duplicata AVISA, não funde** — 409 `talento_ja_existe` **nomeando quem é**
  (id, nome, e-mail, status e se casou por e-mail ou por nome+telefone), com
  `forcar` para o homônimo legítimo, registrado em auditoria. É a regra da casa
  para equivalência assistida (jornadas, incidência, cargos do Tirvu): o sistema
  PROPÕE, o humano confirma. Merge cego cria associação errada que ninguém vê
  depois.
- **Consentimento LGPD fica NULO de propósito** — no cadastro pelo RH ninguém
  marcou nada, e `cadastrado_por_id`/`_nome` (snapshot) dizem quem assumiu. O
  registro descreve o ato REAL, nunca a versão conveniente. **O MCP não pode
  carimbar consentimento**: passaria em qualquer revisão de código (o cadastro
  funciona igual) e o que se perde é a verdade de um registro de LGPD.
- **Currículo** entra por `POST /rh/talentos/{id}/curriculo`, que compartilha o
  `_guardar_curriculo` com a porta pública.

**Implicação para quem for implementar:** a ferramenta `cadastrar_talento` do MCP
é uma casca sobre essa rota. Reimplementar a regra de duplicidade em outro lugar
faria duas portas do mesmo Banco de Talentos discordarem sobre o que é a mesma
pessoa.

## 4. Arquitetura: local primeiro

Três opções avaliadas:

- **(A) MCP local, no desktop** — processo no computador do Bruno, falando com a
  API por HTTPS com um token. **Escolhido para a v1.**
- **(B) MCP remoto, no container** — endpoint HTTP no VPS, com OAuth. Caminho de
  promoção quando o uso provar que vale.
- **(C) Rotas MCP dentro da própria API FastAPI** — **rejeitado**. Funde a
  superfície de "IA que fala" com a de "humano que clica". A IA é um *confused
  deputy*: executa instrução que veio de texto, e neste sistema o texto vem de
  currículo, anotação de CRM e campo livre.

Começar local significa que **um token vazado compromete um desktop, não expõe um
endpoint público**.

## 5. Segurança — as condições inegociáveis

Nenhuma delas é cara. Foram escolhidas por isso: as caras (OAuth, endpoint
público) ficaram para a v2.

### 5.1 Papel próprio, nunca o papel do Bruno

Um `UsuarioRH` `mcp-automacao` com papel dedicado. **Não é burocracia**: é a
diferença entre a auditoria mostrar "a automação leu 1.171 CPFs" com nome próprio
ou misturar isso com o que o Bruno fez à mão. O modelo de papéis da v2.86 já
sustenta isso.

### 5.2 O papel do MCP NÃO recebe `dados:exportar_base`

O eixo da permissão é a **natureza do ato**, não o arquivo (v2.86): *"um `GET`
que devolve a base com CPF é `dados:exportar_base`, nunca `:ler`"*. Um MCP de
diagnóstico não tem por que puxar a base inteira.

### 5.3 Auditoria marcada como MCP

Toda chamada registra que veio da automação. Sem isso, no dia em que algo
estranho acontecer, ninguém sabe se foi gente ou máquina.

### 5.4 Texto que volta ao modelo é DADO, nunca instrução

Anotação de CRM, observação de ficha, motivo de rejeição, currículo: tudo isso é
texto que **alguém de fora digitou**. A regra é do próprio Bruno (v1.99) e o
sistema já tem a defesa escrita — `services/anti_prompt_injection.py`, criada
porque *white text resume injection* é ataque real de mercado. Ela precisa valer
aqui também: currículo é a entrada mais hostil do sistema, e 14 mil deles vêm de
gente desconhecida.

⚠️ **Detecção é REPORTADA, nunca filtrada em silêncio** — o mesmo princípio do
ranking de match, onde currículo suspeito aparece marcado e não sumido.

### 5.5 Mascaramento na saída

CPF mascarado por padrão nas ferramentas de leitura. O MCP existe para responder
*por quê*, não para exportar dado pessoal.

## 6. As ferramentas da v1

Ferramenta demais degrada a escolha do modelo. Seis de leitura, uma de escrita:

```
# Diagnóstico — a metade que responde POR QUÊ
buscar_candidato(nome|cpf|matricula)  → ficha resumida, CPF mascarado
pendencias_admissao(candidato_id)     → o que falta, com motivo
status_documentos(candidato_id)       → slots e status
diagnostico_dossie(candidato_id)      → por que não gerou   ← o caso Luciano
listar_admissoes(filtros)             → fila de trabalho
pendencias_tirvu()                    → o que trava o export

# Escrita — porta ÚNICA e estreita
cadastrar_talento(dados, curriculo?)  → casca sobre POST /rh/talentos
```

**Nada além disso na v1.** Sem efetivar, sem desligar, sem exportar base, sem
criar usuário.

## 7. Os 14 mil: medir antes de agir em massa

**Não processar 14 mil de uma vez.** Lote de 50, medir a taxa de acerto, ajustar.

A regra vem de um caso medido (v2.12): a fila de duplicidade de jornadas tinha
325 itens e, ao ser medida contra os dados reais, **só 3 eram duplicata de
verdade**. Resolver 199 "em massa" teria sido o merge cego que o módulo existia
para impedir.

> **Quando o RH pede velocidade, conferir antes se a fila não está cheia de
> ruído — velocidade em fila errada multiplica erro.**

Casos que aparecerão às centenas em 14 mil, e que precisam de decisão explícita
antes do primeiro lote:

- currículo em `.doc` antigo (o sistema já converte via LibreOffice);
- PDF que é **foto escaneada sem camada de texto** (cai no OCR; pode não render
  nada útil);
- e-mail **sem anexo**, com o currículo colado no corpo;
- a mesma pessoa que mandou currículo três vezes em anos diferentes — o 409 de
  duplicata cobre, mas o volume dirá se a regra atual (e-mail, ou
  nome+telefone) basta;
- currículo de menor de idade ou dado sensível não solicitado.

## 8. Documentação — por que ela é funcional, não burocrática

A descrição de cada ferramenta é **o que o modelo lê para decidir se a usa**.
Descrição ruim = ferramenta errada chamada. Três peças:

1. **Este documento** — o que é, o que expõe, o que deliberadamente não expõe.
2. **Contrato por ferramenta** — entrada, saída, permissão exigida, o que é
   mascarado.
3. **Runbook** — como gerar o token, **como revogar**, o que fazer se vazar. É o
   que ninguém escreve e o único que importa às 3 da manhã.

## 9. O que este desenho deliberadamente NÃO faz

| Não faz | Por quê |
|---|---|
| Ler e-mail pelo servidor | `Mail.Read` alcança a caixa inteira (§ 2) |
| Rotas MCP dentro da API | Funde a superfície da IA com a do humano (§ 4) |
| Reimplementar dedup | Duas portas discordariam sobre a mesma pessoa (§ 3) |
| Carimbar consentimento LGPD | O registro descreve o ato real (§ 3) |
| Processar 14 mil de uma vez | Velocidade em fila errada multiplica erro (§ 7) |
| Efetivar, desligar, exportar base | Fora da v1, por desenho (§ 6) |

## 10. Ordem de execução

1. Papel `mcp-automacao` + token + auditoria marcada (§ 5.1–5.3).
2. As seis ferramentas de **leitura** — valor imediato no diagnóstico, risco
   baixo, e provam o contrato antes de existir escrita.
3. `cadastrar_talento` como casca sobre a rota existente (§ 3).
4. **Lote-piloto de 50 currículos**, medido e relatado (§ 7).
5. Só então decidir sobre volume maior e sobre promover para (B).
