> **Origem.** Gerado com `bmad-create-story` e IMPLEMENTADO com `bmad-dev-story`,
> em 02/09/2026. **Esta é a cópia canônica versionada**, com o registro de
> execução ao final.

---

# Story 1.4: A opcionalidade das colunas novas fica travada em teste

Status: review

Épico 1 (Onda 1, 24ª leva) · Contrato: `docs/planejamento/19-feedbacks-24a-leva.md`

## Story

As a analista de RH,
I want que ninguém torne obrigatório, no futuro, um dos seis campos novos do Tirvu,
so that a falta de um RG ou de um cartão do DF Trans nunca me impeça de mandar a
pessoa para a folha.

## Acceptance Criteria

**AC1 — o comportamento já existe.** A exportação de quem não tem os seis campos
funciona; o trabalho aqui é travá-la em teste, não construí-la.

**AC2 — a mutação reprova nomeando o campo.** Acrescentar um dos seis às
pendências obrigatórias faz o teste falhar dizendo qual campo passou a bloquear.

**AC3 — o layout de 28 colunas continua aceito**, e o teste registra isso.

## Tasks / Subtasks

- [x] **Task 1 — verificar que os três critérios estão satisfeitos**
  - [x] Confirmar o bloco de opcionalidade no teste
  - [x] Rodar a mutação e confirmar que reprova
  - [x] Confirmar a asserção sobre o layout de 28 colunas

---

## Dev Notes

Esta história foi **inteiramente satisfeita pela 1.3**, e isso não é acidente: o
próprio documento de épicos determina que *"a opcionalidade vale desde a 1.3 —
ela não espera a 1.4"*. A separação existia para evitar dependência para a
frente, não para dividir trabalho.

Nada foi implementado aqui. O que se fez foi **verificar**, com execução, que os
três critérios estão cumpridos — e registrar a prova.

## Dev Agent Record

### Agent Model Used

claude-opus-5 (1M context)

### Completion Notes List

**Nenhum código escrito. Nenhum teste acrescentado.** Registrar trabalho que não
houve seria pior do que fechar a história vazia.

Os três critérios foram verificados por execução, não por leitura:

**AC1 — a opcionalidade funciona.** O bloco *"as seis são OPCIONAIS: sem elas,
exporta igual e não vira pendência"* (`test_export_tirvu.py:271`) afirma que as
seis colunas saem vazias, que nenhuma entra em `pendencias_linha`, e que a
planilha de quem não tem os campos continua saindo com as 34 colunas. Passa.

**AC2 — a mutação reprova nomeando o campo.** Rodada agora, acrescentando
`"Nº Cartão DF Trans"` à lista de pendências obrigatórias. O teste falhou com:

> `Nº Cartão DF Trans virou PENDÊNCIA — as seis colunas novas são opcionais e o
> layout de 28 continua aceito; exigi-las bloquearia o export de quem hoje sai
> sem problema`

A mensagem diz **qual** campo e **por que** aquilo é errado, que é o critério.
Código restaurado e conferido: zero resíduo de mutação.

**AC3 — o layout de 28 continua aceito.** O teste (`test_export_tirvu.py:205-211`)
compara o modelo ANTIGO do fornecedor com o novo e exige que as 28 colunas sejam
o **prefixo exato** das 34. É o que sustenta a compatibilidade: se alguém
reordenar as antigas, reprova.

### File List

Nenhum arquivo alterado.

### Change Log

- 02/09/2026 — História verificada e fechada sem alterações: os três critérios já
  eram cumpridos pela entrega da 1.3, conforme o próprio documento de épicos
  previa. Verificação por execução, incluindo a mutação.
