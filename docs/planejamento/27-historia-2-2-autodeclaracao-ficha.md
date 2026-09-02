> **Origem.** Implementada com `bmad-dev-story` em 02/09/2026. **Esta é a cópia
> canônica versionada**, com o registro de execução ao final.

---

# Story 2.2: O RH gera a autodeclaração de residência pela ficha

Status: review

Épico 2 (Onda 1, 24ª leva) · Contrato: `docs/planejamento/19-feedbacks-24a-leva.md`

## Story

As a analista de RH,
I want emitir a autodeclaração de residência a partir da página da pessoa,
so that eu não dependa de o candidato ter declarado comprovante de terceiro no
wizard.

## Acceptance Criteria

**AC1** — um clique na ficha cria o documento, que segue o fluxo normal de
assinatura, usando o gerador que já existe.
**AC2** — quem já tem a autodeclaração pendente ou assinada recebe recusa que
nomeia o estado, sem criar um segundo documento.
**AC3** — a rota declara a permissão do ato.
**AC4** — motivo obrigatório, na auditoria.

## Tasks / Subtasks

- [x] **Task 1 — a rota** (AC1, AC2, AC3, AC4)
- [x] **Task 2 — a porta na tela** (AC1)
- [x] **Task 3 — teste com mutações** (AC1 a AC4)

---

## Dev Agent Record

### Agent Model Used

claude-opus-5 (1M context)

### Completion Notes List

**O gerador sempre existiu; faltava a porta.** O documento só nascia dentro do
wizard, quando o candidato declara que o comprovante está no nome de outra
pessoa. Se ele não declarou — ou se o caso apareceu depois, que é o normal — o RH
não tinha como emitir. É o padrão da v3.16: *ação que só existe dentro de outra
ação não tem porta*.

**Decisão: a autodeclaração entra na lista de documentos avulsos que já existe,
não num bloco próprio.** É a mesma natureza dos documentos de cobertura —
avulso, para uma pessoa, com motivo obrigatório, por decisão do RH. Um segundo
bloco competiria por atenção e repetiria o formulário inteiro por uma opção a
mais. O título do bloco passou de *"Acrescentar documento específico (cobertura,
caso excepcional)"* para *"Emitir documento avulso (cobertura ou
autodeclaração)"*.

**Decisão: NÃO entrou em `DOCS_ESPECIFICOS_DISPONIVEIS`.** Aquele catálogo
alimenta o **kit por posto** (`postos.py` o usa em cinco lugares). Pôr a
autodeclaração ali a ofereceria como documento de posto — e bastaria alguém
marcá-la num kit para passar a exigi-la de **todo mundo daquele posto**. Ela é
documento da PESSOA. Daí rota própria, e a listagem devolvendo
`tem_autodeclaracao` à parte.

**A listagem diz quem já tem.** Sem isso a tela ofereceria a opção a quem já
possui o documento, e o RH levaria um 409 que o sistema podia ter evitado — a
mesma razão pela qual a rota de documentos específicos já devolve `ja_tem`.

**Três mutações validadas**, todas reprovando:

| Mutação | O que o teste disse |
|---|---|
| aceitar motivo vazio | "veio 200" e "a recusa não criou documento nenhum (achou 1)" |
| deixar duplicar | "a segunda emissão responde 409 (veio 200)" e "achou 2" |
| `tem_autodeclaracao` sempre False | "quem JÁ tem é marcado" |

**Duas armadilhas de teste pagas:**

1. O campo da auditoria chama-se `acao`, não `evento` — o teste estourava
   `AttributeError` antes de afirmar qualquer coisa.
2. A limpeza precisou de **dois commits**: no mesmo, o SQLAlchemy ordena os
   DELETEs por tabela e o do candidato saía antes do da auditoria, que tem FK
   para ele. O sintoma é `ForeignKeyViolation` numa limpeza que parece estar na
   ordem certa no código.

**Verificado na tela**, não só no teste: o bloco abre na ficha com o título novo,
o texto explica os dois casos, e a autodeclaração aparece na lista suspensa junto
dos documentos de cobertura.

### File List

| Arquivo | O quê |
|---|---|
| `backend/app/api/revisao.py` | rota `POST .../autodeclaracao-residencia`; `tem_autodeclaracao` na listagem |
| `frontend/src/api.js` | `emitirAutodeclaracaoResidencia` |
| `frontend/src/rh/Detalhe.jsx` | a opção na lista de documentos avulsos, roteando para a rota certa |
| `backend/tests/test_autodeclaracao_ficha.py` | NOVO — 6 blocos, 3 mutações validadas |
| `.github/workflows/ci.yml` | registra o teste novo |

### Change Log

- 02/09/2026 — História 2.2 implementada. A autodeclaração de residência passou a
  ter porta na ficha, com motivo obrigatório e sem duplicar assinatura viva.
