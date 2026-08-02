# Desenhos da 21ª leva — o que ficou para implementar depois

> Status: **DESENHO**, não implementado. Decisão do Bruno em 2026-08-02, ao
> fechar o escopo da v2.54: *"só desenhar os três, implementar depois"*.
>
> Os três itens abaixo mexem em fluxo já existente ou criam módulo novo, e cada
> um tem pelo menos uma decisão que não é técnica. Desenhar antes é o mesmo
> caminho que o multi-signatário seguiu (`04-multi-signatario-plano.md`), onde a
> revisão adversária achou 14 correções obrigatórias ANTES de existir código.

---

## 1. Decisão por filho no reembolso-creche

### O problema, nas palavras do Bruno

> *"se a pessoa tem mais de um filho e um eu defiro e outro eu indefiro, não tem
> opção individual por filho, somente indeferir tudo ou aprovar tudo, não tá
> legal isso. Tem que ser individual isso de modo que eu marco os que defiro e
> os que indefiro, para gerar apenas um requerimento."*

### Como está hoje

`CriancaCreche` (`models/beneficio.py:92-110`) **não tem nenhum campo de
decisão**: só `nome`, `data_nascimento`, `parentesco`, `certidao_key`,
`guarda_key`, `tipo_comprovante`. A decisão vive toda no `BeneficioCreche`
(`status`, `motivo_indeferimento`, `revisado_por/em`).

As rotas de decisão são todas por benefício inteiro: `/ativar`, `/indeferir`,
`/devolver`, `/reabrir`, `/suspender`, `/sem-direito`. Nenhuma recebe
`crianca_id` (a única rota com esse parâmetro serve arquivo).

**O workaround atual é destrutivo**: para aprovar um filho e negar outro, o RH
devolve o levantamento e pede que o colaborador REMOVA a criança
(`creche_publico.py::del_crianca`). Isso apaga a trilha de que aquela criança
foi analisada e negada — e é justamente o registro que prova que o RH avaliou.

### Desenho proposto

**Modelo** — migração ADITIVA em `CriancaCreche`:

| campo | tipo | observação |
|---|---|---|
| `decisao` | `String(12)` nulo | `deferida` / `indeferida`; `NULL` = ainda não decidida |
| `motivo_decisao` | `String(400)` nulo | obrigatório quando `indeferida` |
| `decidido_por` | `String(200)` nulo | SNAPSHOT do e-mail do RH, não FK (mesma regra do mini-CRM) |
| `decidido_em` | `DateTime(tz)` nulo | |

Nada é removido; benefícios existentes seguem com `decisao = NULL` e continuam
funcionando pelo caminho antigo.

**Rota nova**

```
POST /rh/creche/levantamentos/{beneficio_id}/criancas/{crianca_id}/decidir
     { decisao: "deferida" | "indeferida", motivo: str | None }
```

Valida `crianca.beneficio_id == beneficio_id` antes de qualquer coisa — como
`baixar_doc_crianca` já faz. Sem essa checagem, o id de uma criança de outro
benefício seria aceito.

**O status do benefício passa a ser DERIVADO**

`ativar_beneficio` exige que toda criança tenha decisão. Então:

- pelo menos uma `deferida` → benefício `ativo`;
- todas `indeferida` → benefício `indeferido`, com o motivo agregado.

E o `_dump_beneficio` recalcula `algum_elegivel` e `revisar_idade` olhando **só
as deferidas** — hoje uma criança fora da idade contamina o cálculo do benefício
inteiro, que é como o caso do Raul virou alarme de glosa.

**Um requerimento só**

`creche_pdf.py:69-73` já itera `beneficio.criancas`. Basta filtrar por
`decisao == "deferida"` e listar as indeferidas numa seção própria, com o
motivo. Um PDF, um roteiro de assinatura (`criar_roteiro_creche`), nenhum
requerimento duplicado — que é exatamente o que o Bruno pediu.

### As três decisões que não são técnicas

1. **O colaborador vê o motivo do indeferimento por filho?** A regra da casa
   (v2.14, portal `/meu`) é que o motivo da recusa é visível. Aqui isso significa
   dizer a alguém "o benefício do seu filho A foi negado porque…". Provavelmente
   sim, mas é decisão do Bruno.
2. **Decidir por filho vale para benefício já ATIVO?** Se uma criança sai da
   idade, hoje se suspende o benefício todo. Com decisão por filho, dá para
   indeferir só ela e manter o resto — muda o valor pago, então é assunto de DP.
3. **Quem já foi aprovado no modelo antigo migra?** Proposta: **não**. Fica com
   `decisao = NULL` e é tratado como "deferido pelo modelo anterior". Migrar em
   lote gravaria uma decisão que ninguém tomou.

---

## 2. Admissão presencial assistida

### O problema, nas palavras do Bruno

> *"quero pensar em uma estratégia para os casos em que a pessoa tiver baixo
> grau de instrução, ou dificuldades, para que elas quando chegarem na empresa,
> o RH fazer tudo, desde a inserção de dados, coleta de documentos e tudo mais e
> ver alguma forma que a pessoa possa assinar o documento. Pois hoje o RH gera o
> link mas fica inserindo tudo na mão como se fosse uma correção e não como se o
> candidato estivesse ali, ao lado dele."*

### O que este item realmente é

Não é "facilitar o cadastro" — **isso já acontece hoje**, disfarçado de correção
de ficha. O que falta é o sistema **registrar a verdade**: que aquela sessão foi
operada pelo RH, com a pessoa presente.

E aí está a questão séria: o sistema inteiro se apoia em 2FA por e-mail para
provar que quem assinou foi a pessoa. Se o RH digita tudo e clica em assinar, o
manifesto dirá que o candidato assinou — e não foi ele que operou. Hoje isso
acontece **sem deixar rastro de que foi assistido**, o que é pior que fazê-lo
explicitamente.

### Desenho proposto

**Uma sessão assistida, declarada como tal.**

```
POST /rh/candidatos/{id}/sessao-assistida    → abre, registra quem do RH opera
POST /rh/candidatos/{id}/sessao-assistida/encerrar
```

Enquanto aberta:

- o painel do RH mostra uma **faixa permanente** ("sessão assistida — você está
  preenchendo no lugar de Fulano, presente");
- toda escrita vai para a auditoria com `ator="rh_assistido"` e o e-mail do
  operador, além do `candidato_id`;
- ao final, a assinatura é colhida **na tela, com a pessoa presente**.

**A assinatura, que é o ponto delicado.** Três opções, em ordem de força
probatória:

| opção | prova | viabilidade |
|---|---|---|
| Código no celular **dela** (SMS/WhatsApp) | forte — fator que só ela tem | depende de ela ter celular; muitos têm |
| Desenho na tela + declaração do RH | fraca sozinha; boa como presença | funciona sempre |
| Testemunha do RH assinando junto | média | exige segunda pessoa |

**Qualquer que seja, o manifesto NÃO PODE dizer "Fulano assinou eletronicamente
pelo portal".** Tem que dizer o que aconteceu: *"colhido presencialmente em
[data], assistido por [nome do RH], na sede da Green House"*. O precedente exato
já existe no projeto: a `AutorizacaoEquipe` diz *"emitido sob autorização
permanente de X"*, e não *"X assinou"* — a regra da casa é que o manifesto
descreve o ato real, nunca o simula.

### Decisões pendentes do Bruno

1. **Qual das três formas de assinatura** (ou combinação).
2. **O documento assistido tem validade igual ao remoto?** Se um dia for
   contestado, o que se apresenta é o manifesto — que dirá "assistido". É
   preciso que o Bruno esteja de acordo com essa diferença estar escrita.
3. **Quem pode abrir sessão assistida?** Todo usuário do RH ou perfil
   específico?

---

## 3. Câmera e papel timbrado em TODOS os fluxos de upload

### O pedido

> *"ainda sobre o reembolso creche ou qualquer outra área que a pessoa tem que
> subir fotos, documentos ou arquivos, quero que utilize o que montamos e
> validamos de câmera, ficou legal, bem como, para o RH e/ou quando gerar o
> dossiê, já vir no padrão conforme documentos anteriores no timbrado da
> empresa."*

### O achado: o problema é estrutural e triplo

Os dois componentes canônicos existem, são maduros e estão bem construídos:

- **`candidato/Camera.jsx`** (`CapturaDocumento`) — moldura por formato, análise
  de nitidez ~3×/s, disparo manual, flash, editor de recorte, e um fallback
  completo para quando não há câmera. API de 6 props.
- **`services/normalizacao.py`** — `normalizar_para_pdf` → `_pagina_timbrada`,
  que reduz e centraliza a foto numa A4 com marca d'água, topo, rodapé e o
  rótulo do documento.

**Só que três fluxos foram escritos por fora deles**, gravando o arquivo cru no
MinIO:

| fluxo | arquivo | o que grava |
|---|---|---|
| Creche (docs da criança) | `creche_publico.py:617-639` e `:852-870` | `storage.salvar(key, conteudo, ...)` cru |
| Portal do colaborador | `portal.py:621-646` | idem |
| Banco de talentos (currículo) | `talentos.py:199-231` | idem — aqui é intencional (currículo é documento de terceiro, guardado original) |

O que se perde no creche e no portal: papel timbrado, conversão para PDF,
validação de nitidez (`imagem_borrada`), dimensão mínima, teto de 50MB e
checagem de formato (`ext or "bin"` aceita qualquer coisa).

### Desenho proposto

**Backend** — creche e portal passam a chamar `normalizar_para_pdf` +
`combinar_pdfs`, exatamente como `documentos.py` e `rh_ficha.py` já fazem.
O currículo do Banco de Talentos **continua cru** de propósito: é documento de
terceiro e o RH precisa dele como veio (a conversão para exibição já existe e
basta).

**Frontend** — `CrecheLink.jsx:511-517` e `Portal.jsx:543` trocam o
`<input type="file">` solto pelo `<CapturaDocumento formato="a4" …>`, com o
mesmo padrão de uso do `Checklist.jsx:320-324` (a mesma função nas duas
callbacks).

### ⚠️ Achado fora do pedido: isto tem uma parte que é SEGURANÇA, não experiência

Separando com cuidado, porque o Bruno mandou só desenhar:

- **Desenho** (fica para depois): câmera guiada e papel timbrado. É experiência.
- **Conserto** (deveria entrar antes): os mesmos três endpoints **não fecham o
  arquivo** (`await arquivo.close()`), não têm teto de tamanho e aceitam
  qualquer extensão — numa rota **pública**.

O `close()` não é detalhe: o CLAUDE.md registra que o Starlette faz spool em
disco acima de ~1MB. Sem fechar, sobra **certidão de nascimento de criança** num
temp file dentro do container. Os uploads que fazem certo (`talentos.py:217`,
`portal.py:642`) já fecham no `finally` — é regra da casa que estes três
furaram.

**Recomendação:** tratar o `close()` + teto de tamanho + validação de extensão
como conserto de segurança na próxima leva, independentemente de quando a câmera
e o timbrado forem implementados.

---

## Resumo do que decidir antes de codificar

| item | decisão que só o Bruno toma |
|---|---|
| Decisão por filho | motivo visível ao colaborador? vale para ativo? migra o histórico? |
| Admissão assistida | qual forma de assinatura? o manifesto pode dizer "assistido"? quem pode abrir? |
| Câmera/timbrado | nenhuma — mas o conserto de segurança dos uploads não deveria esperar |
