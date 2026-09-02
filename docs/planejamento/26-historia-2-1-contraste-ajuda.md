> **Origem.** Implementada com `bmad-dev-story` em 02/09/2026. **Esta é a cópia
> canônica versionada**, com o registro de execução ao final.

---

# Story 2.1: A interrogação de ajuda é legível no tema escuro

Status: review

Épico 2 (Onda 1, 24ª leva) · Contrato: `docs/planejamento/19-feedbacks-24a-leva.md`

## Story

As a candidato usando o portal no tema escuro,
I want enxergar o botão de ajuda,
so that eu consiga pedir explicação quando travo numa etapa.

## Acceptance Criteria

**AC1** — contraste ≥ 4,5:1 no tema escuro, **medido no navegador**, nas telas do
portal do candidato.
**AC2** — contraste ≥ 4,5:1 no tema claro, sem regressão.
**AC3** — a regra usa tokens que invertem juntos, no mesmo desenho do `.ajuda-q`;
nenhum valor de cor fixo é escrito para resolver o caso.

## Tasks / Subtasks

- [x] **Task 1 — corrigir a regra** (AC1, AC2, AC3)
  - [x] Trocar o par `var(--tinta)` + `#fff` por tokens que invertem juntos
  - [x] Medir no navegador, nos dois temas
- [x] **Task 2 — impedir a volta**
  - [x] Bloco 3b no `test_design_system.py` (já roda no CI)
  - [x] Ciclo vermelho-verde de verdade: com o defeito, reprova nomeando a regra

---

## Dev Notes

O defeito estava rastreado até a linha desde o SPEC (`styles.css:609`), e a
correção irmã já existia no `.ajuda-q` do painel do RH (v2.46). Este botão é do
portal do CANDIDATO e ficou para trás.

## Dev Agent Record

### Agent Model Used

claude-opus-5 (1M context)

### Completion Notes List

**O defeito, medido antes de corrigir.** A regra era:

```css
.btn-ajuda { background: var(--tinta); color: #fff; }
```

Cada metade parece inofensiva. Juntas produzem o defeito: `--tinta` **inverte**
com o tema (quase-preto no claro, `#e9f4ec` no escuro) e o `#fff` **não**. No
tema escuro era "?" branco sobre círculo branco.

Medido no navegador, com a fórmula do WCAG sobre o estilo computado:

| Tema | Antes | Depois | Mínimo |
|---|---|---|---|
| claro | 16,28:1 | 4,77:1 | 4,5:1 |
| escuro | **1,13:1** | **5,94:1** | 4,5:1 |

O valor no claro caiu e continua acima do mínimo: a correção troca um botão de
alto contraste por um discreto, que é o desenho do `.ajuda-q` — ajuda é apoio,
não ação principal.

**Ciclo vermelho-verde real, no navegador.** O `_contraste-ajuda.spec.js` mediu
**1,13:1** antes de o container ser reconstruído (o defeito ainda servido) e
**5,94:1** depois. Não foi cálculo no papel: o valor sai do `getComputedStyle` da
página real.

**A trava é estrutural e pega a CLASSE do defeito, não o caso.** O bloco 3b do
`test_design_system.py` (que já roda no CI) reprova qualquer regra que misture
cor **fixa** com token que **inverte** — `background: var(--token)` ao lado de
`color: #hex`, ou o contrário. Verificado por mutação: restaurando a regra
antiga, ele falha dizendo

> `.btn-ajuda (background: var(--tinta) + color: #fff)`

Dois cuidados para o teste não virar ruído: tokens de **marca e sinal** ficam de
fora (o verde da casa é o mesmo nos dois temas, então `#fff` sobre `var(--verde)`
é legítimo), e comentários são removidos antes da varredura — a explicação de um
defeito não pode ser confundida com o defeito (v2.71).

**Por que o teste de tela injeta o botão.** As três telas onde ele vive exigem
token de candidato válido, que não existe num teste avulso. Como o que se mede é
a **regra de CSS**, a mesma para as três, o botão é inserido na página real, que
já carregou a folha de estilos de produção. O estilo computado é o de verdade; só
o contexto de navegação é sintético.

### File List

| Arquivo | O quê |
|---|---|
| `frontend/src/styles.css` | `.btn-ajuda` com tokens que invertem juntos |
| `backend/tests/test_design_system.py` | bloco 3b: cor fixa + token que inverte |
| `frontend/tests/e2e/_contraste-ajuda.spec.js` | NOVO — mede o contraste no navegador |

### Change Log

- 02/09/2026 — História 2.1 implementada. O "?" do portal do candidato passou de
  1,13:1 para 5,94:1 no tema escuro.
