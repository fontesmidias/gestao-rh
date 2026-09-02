> **Origem.** Gerado com `bmad-create-story` e IMPLEMENTADO com `bmad-dev-story`,
> em 02/09/2026. **Esta é a cópia canônica versionada**, com o registro de
> execução ao final.

---

# Story 1.3: A planilha do Tirvu sai com as 34 colunas do modelo novo

Status: review

Épico 1 (Onda 1, 24ª leva) · Contrato: `docs/planejamento/19-feedbacks-24a-leva.md` ·
Épicos: `docs/planejamento/20-epicos-24a-leva-onda-1.md`

## Story

As a analista de RH,
I want que o arquivo gerado tenha as 34 colunas que o Tirvu passou a exigir,
so that a importação seja aceita sem eu ter de completar colunas à mão.

## Contexto: é ligar, não coletar

O Bruno trouxe o layout novo em 02/09/2026, com o arquivo
`docs/Layout de Importação de Admissões (1).xlsx` (item 16 da leva).

**Os dois arquivos foram abertos e comparados.** O modelo novo tem **34 colunas**
na aba `Plan1`; as **28 primeiras são idênticas às atuais, na mesma ordem**. As 6
novas são AC a AH.

**Os seis campos já são coletados** — nenhuma pergunta nova ao candidato, nenhuma
migration:

| Col | Cabeçalho | Campo | Modelo |
|---|---|---|---|
| AC | Nome do Pai | `nome_pai` | `DadosPessoais` (`ficha.py:87`) |
| AD | Nome da Mãe | `nome_mae` | `DadosPessoais` (`ficha.py:86`) |
| AE | Nº Cartão DF Trans | `cartao_dftrans` | **`ValeTransporte`** (`ficha.py:204`) |
| AF | Nº do RG | `rg_numero` | `DocumentosIdentificacao` (`ficha.py:141`) |
| AG | Órgão Expedidor do RG | `rg_orgao_emissor` | `DocumentosIdentificacao` (`ficha.py:142`) |
| AH | Data de Emissão do RG | `rg_data_expedicao` | `DocumentosIdentificacao` (`ficha.py:143`) |

⚠️ **`linha_tirvu` não carrega `ValeTransporte` hoje.** Ela busca `DadosPessoais`,
`Endereco`, `DocumentosIdentificacao`, `PostoServico`, `Jornada` e `Empresa`
(`export_tirvu.py:220-227`). O DF Trans exige um `db.get` a mais.

## Acceptance Criteria

**AC1 — 34 colunas, na ordem do fornecedor.**
A planilha sai com as 34 colunas do modelo, na aba `Plan1`, na mesma ordem. As 28
primeiras permanecem idênticas, sem reordenação.

**AC2 — os seis campos saem preenchidos para quem tem o dado.**
Nome do pai, nome da mãe, cartão do DF Trans, número do RG, órgão expedidor e data
de emissão vêm do que o sistema já coleta. Nenhum campo novo é perguntado e
nenhuma migration de coleta é criada.

**AC3 — o DF Trans sai como TEXTO.**
Um cartão que começa com zero preserva o zero. Existe teste que reprova se a
célula for gravada como número.

**AC4 — a data do RG sai no formato do layout.**
`dd/mm/aaaa`, como as demais datas da planilha.

**AC5 — as seis colunas são opcionais.**
Quem não tem nenhum dos seis exporta normalmente, com as células vazias, e **não
vira pendência**. O layout de 28 colunas continua aceito.

**AC6 — coberto por teste, contra o arquivo do fornecedor.**
O teste compara com `docs/Layout de Importação de Admissões (1).xlsx`, não com uma
lista de cabeçalhos escrita no teste.

## Tasks / Subtasks

- [x] **Task 1 — as colunas** (AC1)
  - [x] Acrescentar as 6 entradas ao fim de `COLUNAS_TIRVU`, na ordem AC→AH
  - [x] Não tocar nas 28 existentes, nem na ordem delas
  - [x] Atualizar as docstrings que dizem "28 colunas" (`export_tirvu.py:214` e
        `:331`, `colaboradores.py:246`) — não quebram nada, mas passam a mentir
- [x] **Task 2 — os valores** (AC2, AC3, AC4)
  - [x] `linha_tirvu` carrega `ValeTransporte` (é um `db.get` novo)
  - [x] Preencher as 6 colunas a partir dos campos já coletados
  - [x] Data do RG por `_data(...)`, como as demais
  - [x] DF Trans como texto — ver "O zero à esquerda", abaixo
- [x] **Task 3 — opcionalidade** (AC5)
  - [x] Conferir que nenhum dos 6 entra em `pendencias_linha`
- [x] **Task 4 — teste** (AC6)
  - [x] Estender `test_export_tirvu.py` comparando com o `.xlsx` do fornecedor
  - [x] Mutações nomeadas e validadas de verdade

---

## Dev Notes

### O que já foi verificado — não redescubra

Os dois arquivos do fornecedor foram abertos e comparados coluna a coluna
(02/09/2026). O modelo novo tem **só o cabeçalho, sem linha de exemplo** — a mesma
armadilha da v2.83: **ele valida a FORMA, não o CONTEÚDO**. Passar no teste de
layout não prova que os valores estão certos.

Os cabeçalhos exatos das seis, como estão no arquivo (respeite acento e maiúscula):

```
Nome do Pai · Nome da Mãe · Nº Cartão DF Trans · Nº do RG ·
Órgão Expedidor do RG · Data de Emissão do RG
```

### O zero à esquerda — a regra do fornecedor que vira teste

Orientação registrada no SPEC: **o Nº Cartão DF Trans é TEXTO, nunca número.**
Como número, o Excel come o zero à esquerda e o cartão entra errado na integração.

Medido nesta máquina: o `openpyxl` **preserva** string com zero à esquerda
(`data_type == 's'`) e grava número como número (`'n'`). Ou seja, **basta o valor
chegar à célula como `str`**.

O risco real não é o openpyxl — é alguém "limpar" o campo no caminho, por exemplo
aplicando `_so_digitos` e convertendo, ou deixando o valor virar `int`. A coluna
`cartao_dftrans` é `String(40)` no banco, então o valor já nasce texto; **não o
converta**. O teste trava isso conferindo `data_type` da célula, não só o valor —
`"0012345"` e `12345` podem parecer iguais numa comparação frouxa.

### Onde mexer, com o estado atual

**`COLUNAS_TIRVU`** (`export_tirvu.py:47`) tem as 28 entradas em ordem fixa. As
novas vão **ao fim**, na ordem AC→AH.

Verificado: `COLUNAS_TIRVU` só é usada dentro do próprio `export_tirvu.py`
(linhas 347 e 350, ambas `enumerate` — agnósticas ao tamanho). Os consumidores
tratam a linha como dict opaco e nunca contam chaves. **Nada quebra com 34.**

**`linha_tirvu`** (`export_tirvu.py:214`) devolve um dict cujas chaves são os
nomes das colunas. Hoje carrega:

```python
p = db.get(DadosPessoais, c.id)
e = db.get(Endereco, c.id)
d = db.get(DocumentosIdentificacao, c.id)
posto = db.get(PostoServico, c.posto_servico_id) if c.posto_servico_id else None
jornada = db.get(Jornada, c.jornada_id) if c.jornada_id else None
empresa = db.get(Empresa, c.empresa_id) if getattr(c, "empresa_id", None) else None
```

`p` e `d` já servem cinco das seis colunas. **Falta `ValeTransporte`** para o DF
Trans — importe o modelo e busque por `c.id` (é 1:1 com o candidato, como
`DadosPessoais`).

Siga o padrão de guarda que o arquivo inteiro usa: `(p.nome_pai if p else "") or ""`.
Registro ausente é comum (nem todo candidato preencheu tudo), e `None` na célula
faria o `montar_workbook_tirvu` pular — que é o comportamento certo, mas o dict
deve trazer string vazia, como as outras 28.

**`montar_workbook_tirvu`** (`export_tirvu.py:329`) escreve célula a célula e
**omite célula vazia de propósito** — evita o `inlineStr` malformado que o parser
do Tirvu recusa. **Não mexa nisso**; as colunas novas herdam o comportamento.

### A opcionalidade — o que NÃO fazer

`pendencias_linha` (`export_tirvu.py:378`) lista os campos que o Tirvu recusa ou
acusa. **Nenhum dos seis entra ali.**

Não é esquecimento, é a regra do fornecedor: as 6 são opcionais e o layout de 28
continua aceito. Acrescentá-las bloquearia o export de quem não tem RG cadastrado
— gente que hoje é exportada sem problema. É a armadilha do "Registra Ponto"
invertida: lá o campo vazio precisava virar pendência porque o Tirvu o aceitava
calado e o colaborador nascia sem marcação; aqui o campo vazio é legítimo.

O teste do bloco de opcionalidade da história 1.4 vai travar isso por mutação —
mas **a 1.3 já entrega o comportamento**, e não pode esperar por ela.

### Regressões a não causar

- **As 28 primeiras colunas não mudam**, nem em nome nem em ordem nem em valor.
  `test_export_tirvu.py` e `test_tirvu_individual_pendencias.py` cobrem isso.
- **`montar_workbook_tirvu` continua sem autofiltro, sem painel congelado e com a
  aba `Plan1`** — o importador do Tirvu recusa a "decoração" (v1.82).
- **O export por seleção (v3.17) não muda.** Ele chama `linha_tirvu`; acrescentar
  colunas ao dict é transparente para ele.
- **`export_dexion.py` não é tocado.** São 97 colunas, layout independente.
- Documento assinado nunca muda; isto é planilha, não PDF — sem impacto.

### Testes

**Estenda `backend/tests/test_export_tirvu.py`**, que já roda no CI e já tem os
stubs mínimos para `linha_tirvu`. Ele **não precisa de banco** (usa objetos
falsos), o que o torna rápido e o lugar certo para asserção de layout.

Cobrir:

1. **Layout contra o arquivo do fornecedor:** ler
   `docs/Layout de Importação de Admissões (1).xlsx` e comparar as 34 células do
   cabeçalho, na ordem, com `COLUNAS_TIRVU`. **A referência é o arquivo**, não uma
   cópia escrita no teste — cópia à mão diverge do modelo na primeira revisão dele
   e o teste segue verde (v2.54).
2. **Os seis valores** saem preenchidos quando os campos existem.
3. **DF Trans com zero à esquerda:** gerar a planilha, reabrir com `openpyxl` e
   conferir `cell.data_type == "s"` **e** o valor com o zero. Só o valor não basta.
   ⚠️ Use um cartão **preenchido**: `montar_workbook_tirvu` OMITE célula vazia
   (`export_tirvu.py:355`), então com o campo em branco não existe célula para
   ter `data_type` — o teste passaria por não achar nada.
4. **Data do RG** em `dd/mm/aaaa`.
5. **Tudo vazio:** quem não tem os seis exporta, e `pendencias_linha` não acusa
   nenhum deles. Aqui a asserção é sobre a **ausência da célula** (o workbook
   omite vazio), não sobre `data_type`.

**Mutações obrigatórias:**

| Mutação | Deve reprovar |
|---|---|
| gravar o DF Trans como `int` | o bloco 3 |
| acrescentar um dos seis a `pendencias_linha` | o bloco 5 |
| trocar a ordem de duas colunas novas | o bloco 1 |

Confirme que o teste **imprimiu** o resultado — ausência de falha não é aprovação
(v2.72.2).

**Ambiente:** este teste não precisa de containers. Rode
`PYTHONPATH=. .venv/Scripts/python.exe tests/test_export_tirvu.py`.

⚠️ **O teste roda com o diretório atual em `backend/`**, e o modelo do fornecedor
mora em `docs/`, na raiz. Resolva o caminho a partir de `Path(__file__)`, nunca do
diretório atual — senão passa na sua máquina e falha no CI.

⚠️ **Não confie só na extração de texto.** O modelo do fornecedor tem apenas
cabeçalho; se possível, gere uma planilha com dados fictícios e **abra para
conferir** que as colunas novas caíram nas posições AC→AH.

### Project Structure Notes

| Arquivo | Natureza |
|---|---|
| `backend/app/services/export_tirvu.py` | UPDATE — `COLUNAS_TIRVU` e `linha_tirvu` |
| `backend/tests/test_export_tirvu.py` | UPDATE — layout, valores, DF Trans como texto |

Fora de escopo: coleta de campos (já existem), `export_dexion.py`, as telas, e a
opcionalidade travada por mutação (história 1.4).

### References

- [Source: docs/planejamento/19-feedbacks-24a-leva.md#CAP-23] — contrato
- [Source: docs/planejamento/19-feedbacks-24a-leva.md#Anexo — Achados no código] —
  item 16, com a tabela das seis colunas e as três regras do fornecedor
- [Source: docs/Layout de Importação de Admissões (1).xlsx] — o modelo, 34 colunas
- [Source: CLAUDE.md] — planilha do Tirvu recusa decoração; teste de layout compara
  com o arquivo oficial, nunca com cópia à mão (v2.54)

## Dev Agent Record

### Agent Model Used

claude-opus-5 (1M context)

### Debug Log References

- Nenhum container necessário: `test_export_tirvu.py` usa stubs, sem banco.
- Um ajuste durante a implementação: os stubs do teste não declaram os campos
  novos, e `p.nome_pai` estourava `AttributeError`. Trocado para `getattr` com
  padrão — que também é mais correto no código real, porque o registro da seção
  pode simplesmente não existir para quem nunca preencheu.

### Completion Notes List

**Era ligar, não coletar — e foi.** Os seis campos já eram coletados na ficha.
Nenhuma pergunta nova ao candidato, nenhuma migration, nenhuma tela alterada.

**O layout foi comparado com o arquivo do fornecedor, não com uma lista.** O
teste lê `docs/Layout de Importação de Admissões (1).xlsx` e compara as 34
células do cabeçalho com `COLUNAS_TIRVU`. Uma cópia escrita no teste divergiria
do modelo na primeira revisão dele e seguiria verde (v2.54). O caminho sai de
`Path(__file__)`, não do diretório atual — o teste roda com o CWD em `backend/`
e o modelo mora em `docs/`, na raiz.

**Acrescentado um segundo trava que a história não pedia:** o teste também
confere que o layout ANTIGO (28 colunas) continua sendo o **prefixo exato** do
novo. É isso que sustenta a regra do fornecedor de que a planilha de 28 colunas
segue aceita; se alguém reordenar as antigas, o teste reprova nomeando o motivo.

**O DF Trans exigiu uma consulta a mais.** Ele mora em `ValeTransporte`, não em
`DadosPessoais` — era o único dos seis fora dos modelos que `linha_tirvu` já
carregava.

**O zero à esquerda foi verificado na planilha REAL, não só em teste.** Gerei um
arquivo com dados fictícios e conferi as posições: as seis caíram exatamente em
AC→AH, todas com `data_type == "s"`, e `"0012345678"` chegou inteiro. A asserção
é sobre o tipo da célula, não só sobre o valor: numa comparação frouxa, o número
`12345678` passaria por igual.

**Opcionalidade entregue nesta história, não adiada.** Nenhum dos seis entra em
`pendencias_linha`. Quem não tem RG ou DF Trans exporta como sempre exportou —
exigi-los bloquearia gente que hoje sai sem problema. O teste afirma a **ausência
da célula** nesse caso, porque `montar_workbook_tirvu` omite vazio de propósito
(evita o `inlineStr` malformado que o parser do Tirvu recusa).

**Três mutações validadas**, todas reprovando com mensagem que nomeia o defeito:

| Mutação | O que o teste disse |
|---|---|
| DF Trans gravado como `int` | `AssertionError: 12345678` — o zero foi comido |
| acrescentar "Nº do RG" às pendências | "virou PENDÊNCIA — as seis são opcionais…" |
| trocar a ordem de duas colunas novas | "COLUNAS_TIRVU divergiu do modelo oficial" |

**Regressão:** smoke 15/15; `test_tirvu_individual_pendencias`,
`test_export_dexion`, `test_export_por_selecao`,
`test_importacao_massa_nao_regride_export` e `test_matricula` OK. Confirmado que
`COLUNAS_TIRVU` só é usada dentro do próprio módulo, em dois `enumerate`
agnósticos ao tamanho — nada dependia de "exatamente 28".

Docstrings que diziam "28 colunas" atualizadas para 34; ficariam mentindo.

### File List

| Arquivo | O quê |
|---|---|
| `backend/app/services/export_tirvu.py` | 6 colunas em `COLUNAS_TIRVU`, `ValeTransporte` em `linha_tirvu`, valores das colunas novas, docstrings |
| `backend/tests/test_export_tirvu.py` | 4 blocos novos, 3 mutações validadas |

### Change Log

- 02/09/2026 — História 1.3 implementada. A planilha do Tirvu passou a sair com
  as 34 colunas do modelo novo, ligando campos que o sistema já coletava.
