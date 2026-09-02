# 21 — Sprint da Onda 1 (24ª leva)

> **Origem.** Gerado com `bmad-sprint-planning` a partir de
> `20-epicos-24a-leva-onda-1.md`, em 02/09/2026.
>
> **Este é o rastro do item 14 no nível da execução.** O doc 19 diz o que foi
> pedido, o 20 diz o que construir, e este diz **onde cada coisa está agora**.
> Responde "o que da Onda 1 ainda está aberto?" sem reler conversa nenhuma.
>
> O arquivo que as ferramentas leem e escrevem é
> `_bmad-output/implementation-artifacts/sprint-status.yaml` (não versionado).
> **Este arquivo é a cópia canônica versionada** — ao mexer no status, re-derivar
> lá e republicar aqui.

---

## A fila

A ordem é a do anexo de priorização do SPEC: **falha silenciosa antes de falha
visível**. A 1.1 vem primeiro porque a planilha errada da folha é o único defeito
da leva que o RH não tem como perceber sozinho.

| # | História | Épico | Status |
|---|---|---|---|
| 1.1 | [Exportar entrega quem está marcado](22-historia-1-1-exportar-por-selecao.md) | 1 | **review** |
| 1.2 | [Exportar também em Admissões](23-historia-1-2-exportar-admissoes.md) | 1 | **review** |
| 1.3 | [A planilha do Tirvu sai com as 34 colunas](24-historia-1-3-tirvu-34-colunas.md) | 1 | **review** |
| 1.4 | [A opcionalidade das colunas novas fica travada](25-historia-1-4-opcionalidade-travada.md) | 1 | **review** |
| 2.1 | A interrogação de ajuda é legível no tema escuro | 2 | backlog |
| 2.2 | O RH gera a autodeclaração de residência pela ficha | 2 | backlog |
| 2.3 | O link devolve a pessoa à etapa pendente | 2 | backlog |
| 3.1 | A rota de exclusão existe e recusa quem não pode sair | 3 | backlog |
| 3.2 | O RH exclui pela tela da pessoa | 3 | backlog |
| 3.3 | O candidato excluído volta da lixeira | 3 | backlog |

O **Épico 1 está completo**: as quatro histórias (1.1 a 1.4) estão implementadas
e em revisão — docs [22](22-historia-1-1-exportar-por-selecao.md),
[23](23-historia-1-2-exportar-admissoes.md),
[24](24-historia-1-3-tirvu-34-colunas.md) e
[25](25-historia-1-4-opcionalidade-travada.md). As seis dos épicos 2 e 3 seguem em
`backlog`, que aqui significa "existe no documento de épicos, sem arquivo de
história criado ainda".

## Como o status anda

- **Épico:** `backlog` → `in-progress` → `done`. Vira `in-progress` sozinho
  quando a primeira história dele é criada.
- **História:** `backlog` → `ready-for-dev` → `in-progress` → `review` → `done`.
  Vira `ready-for-dev` quando o arquivo da história é criado.
- **Retrospectiva:** `optional` ↔ `done`. As três estão em `optional`.

## O que NÃO está aqui

- **CAP-2b** (os filtros refletirem quem vai para o Tirvu) — adiado pelo Bruno em
  02/09/2026. Continua no SPEC, sem desenho aceito. Não implementar por conta
  própria.
- **Ondas 2 a 5** — CAP-6, CAP-8, CAP-8b, CAP-9 a CAP-21. Registradas no doc 19,
  fora deste sprint.

## Estado bruto

```yaml
development_status:
  epic-1: in-progress
  1-1-exportar-entrega-quem-esta-marcado: review
  1-2-exportar-tambem-em-admissoes: review
  1-3-a-planilha-do-tirvu-sai-com-as-34-colunas-do-modelo-novo: review
  1-4-a-opcionalidade-das-colunas-novas-fica-travada-em-teste: review
  epic-1-retrospective: optional

  epic-2: backlog
  2-1-a-interrogacao-de-ajuda-e-legivel-no-tema-escuro: backlog
  2-2-o-rh-gera-a-autodeclaracao-de-residencia-pela-ficha: backlog
  2-3-o-link-devolve-a-pessoa-a-etapa-pendente: backlog
  epic-2-retrospective: optional

  epic-3: backlog
  3-1-a-rota-de-exclusao-existe-e-recusa-quem-nao-pode-sair: backlog
  3-2-o-rh-exclui-pela-tela-da-pessoa: backlog
  3-3-o-candidato-excluido-volta-da-lixeira: backlog
  epic-3-retrospective: optional
```
