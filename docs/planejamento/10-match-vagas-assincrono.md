# Match de Vagas — processamento assíncrono e multi-provedor (v2.00)

Correção do incidente de 2026-07-28 e evolução pedida pelo Bruno no mesmo dia.
Revisado em roundtable (party-mode) antes da implementação.

---

## O incidente — o que o log provou

```
06:15:42  vaga_criada     "Técnico em Secretariado MME"
06:15:45  vaga_ranqueada  total_talentos:131  curriculos_analisados:18
06:16:52  vaga_ranqueada  total_talentos:131  curriculos_analisados:2
```

Duas execuções da **mesma vaga**, 67 segundos de intervalo, com números
**diferentes e decrescentes**. Isso elimina a hipótese de "os currículos são
ilegíveis" — arquivo quebrado daria o mesmo número nas duas rodadas.

**Causa raiz: rate limit da Groq + kill switch irreversível.**

`match_vagas.py:112-120` (código de v1.99):

```python
for t in talentos:
    if not ia_indisponivel:            # ← 115
        try:
            analise = _analisar_curriculo(vaga, t)
        except IndisponivelError:
            ia_indisponivel = True     # ← 119: NUNCA volta a False
```

Um único HTTP 429 no 19º talento desligou a IA para os 112 restantes — eles
**nem foram tentados**. Na segunda rodada a cota já estava quase esgotada, daí
o 2.

Agravantes que o roundtable levantou:

1. **`429` é tratado igual a `401`.** `ia_texto.py:49-61` captura
   `except Exception` e converte tudo em `IndisponivelError`. Um limite de
   cota (resolve em 60s) é indistinguível de chave inválida (permanente). O
   header `Retry-After` que a Groq envia é descartado.
2. **Nada é persistido.** Cada clique refaz as 131 análises e paga tudo de
   novo. Foi por isso que a 2ª rodada foi **pior** que a 1ª — o sistema pune
   quem clica duas vezes.
3. **Mensagem desonesta.** A tela dizia "IA ficou indisponível", que o RH lê
   como "caiu, vou tentar de novo" — e o segundo clique piorou o resultado.
   Erro transitório e erro permanente não podem falar a mesma coisa.
4. **Timeout do nginx.** `location /api/` usa o default de **60s**
   (`frontend/nginx.conf:19-27`; a exceção de 600s existe só para
   `/api/rh/arquivo/lote`). 131 talentos com OCR levam ~11 min — nunca
   caberiam, mesmo com o rate limit resolvido.
5. **O filtro estruturado não economiza chamada de IA nenhuma**, apesar de o
   docstring de `match_vagas.py:48-63` dizer que "reduz o universo antes de
   gastar chamada de IA". O `bate_filtro` só entra no payload e na ordenação
   final — a IA é chamada para todo mundo.
6. **`.heic` é 100% ilegível** em produção: `pillow-heif` não está no
   `pyproject.toml`, então `Image.open()` falha para foto de iPhone —
   apesar de `.heic` ser aceito no upload (`talentos.py:30`).
7. **`curriculo_nome` NULL ⇒ ilegível.** `extrair_texto` despacha por
   extensão do NOME; talento importado por planilha sem nome de arquivo cai
   em "formato desconhecido" mesmo tendo o arquivo certo no MinIO.

---

## O desenho novo

### Princípio que reorganiza tudo

> *"enquanto a análise é feita, o RH precisa usar o sistema"* — Bruno

O ranqueamento deixa de ser um request síncrono e vira **trabalho de fundo**
no worker RQ que já existe em produção (`deploy/docker-compose.base.yml`).
Isso resolve o timeout do nginx sem tocar em nginx, e permite ao worker ir
**devagar de propósito** — respeitar cota deixa de ser problema e vira escolha
barata, porque ninguém está esperando na tela.

### Três provedores, três papéis

| Papel | Provedor | Por quê |
|---|---|---|
| **Ler** o currículo | Mistral OCR | OCR de verdade — lê PDF escaneado e foto de celular, que o `pypdf` não lê |
| **Analisar** (principal) | OpenRouter | Conta do Bruno **[decidido]** |
| **Analisar** (reserva) | Groq | Assume quando o OpenRouter falha ou estoura cota **[decidido]** |

Se **os dois analisadores** estiverem fora, o worker espera e retoma — nunca
desiste em silêncio como fazia antes.

### Leitura sai do caminho crítico

O texto do currículo **não muda nunca** depois do upload. Logo, não faz
sentido reler 131 currículos a cada clique.

- Extração acontece **uma vez, no upload**, em background (worker).
- **Backfill** dos 131 atuais roda uma vez, devagar, respeitando cota.
- O ranqueamento não faz OCR nenhum — já encontra o texto pronto.

### Decisões do Bruno (2026-07-28)

1. **Reaproveitar análise existente** — talento já analisado para aquela vaga
   não é reprocessado; clicar de novo é praticamente grátis. Botão
   "reanalisar" força quando necessário. *(É a correção direta do que
   transformou 18 em 2.)*
2. **Aviso interno por e-mail ao terminar** — evento novo na matriz de
   `services/notificacoes.py` (nunca mandar para `smtp_from` direto — regra
   da casa). O RH escolhe quem recebe em Configurações.
3. **Sem IA disponível ⇒ entrega ranking só com filtro estruturado**, dizendo
   isso na tela. Algo útil na mão em vez de nada.
4. **Texto do currículo guardado enquanto o talento existir** (cascade), já
   **minimizado** (sem CPF/RG/telefone/e-mail/CEP).

### Aba de Resultados — prestação de contas, não barra de progresso

O pedido do Bruno foi *"tudo para subsidiar melhor as decisões"*. O log
anterior dizia `analisados: 2` e **sumia com os outros 129** — o RH não sabia
se era falta de currículo, falha de leitura ou IA não executada.

Cada pessoa aparece com **o motivo de estar onde está**:

- ✅ analisado — nota + justificativa
- ⭕ sem currículo enviado
- ⚠️ currículo ilegível — **com o formato** (`.heic` tem conserto)
- ⏳ ainda na fila
- 🔁 a IA falhou nesta pessoa — vai tentar de novo
- 🚩 currículo com trecho suspeito (anti-prompt-injection, v1.99)

> **Regra da casa, terceira aparição:** o lote diz quem barrou e por quê.
> Ninguém some em silêncio. (Mesma regra do lote de documento crítico em
> `desenvolvimento.py` e da importação em massa do Tirvu em v1.96.)

### Status do talento que discrimina

Hoje **nada** move `novo → em_analise` — só o clique manual e a conversão.
Por isso todos os 131 estão "Novo" e o campo não significa nada.

Passa a mudar em **ato de atenção do RH**: baixar/visualizar o currículo, ou
abrir as anotações. **NÃO** no ranqueamento em massa — marcar 131 de uma vez
recriaria o mesmo problema com outro rótulo (decisão da Sally no roundtable,
acatada). O status é sobre **o RH** ter olhado, não sobre a máquina ter
processado.

---

## LGPD — o que muda com três provedores

O rol de operadores passa a ter **três nomes**, não um:

- **Mistral** vê o currículo **antes** da minimização — ela precisa, é ela que
  produz o texto. Já era verdade em v1.99; fica registrado, não descoberto
  depois.
- **OpenRouter** e **Groq** veem **só o texto já minimizado** — nenhum dos dois
  analisadores enxerga CPF, RG, telefone, e-mail ou CEP.
- O texto guardado no banco nasce minimizado: se um dia alguém der um `SELECT`
  sem pensar, não há CPF lá dentro.

**Atenção para quem mexer nisso depois:** o `zdr_ativo` da Mistral existe para
**atestado de saúde**, não para currículo. Currículo vai para a Mistral
**independente** do `zdr_ativo` — isso é intencional (o consentimento do Banco
de Talentos cobre a finalidade de recrutamento), não descuido.

---

## Ordem de execução

O que faz a tela funcionar **hoje** primeiro; o resto depois.

1. **Parar de morrer na 19ª** — retry com backoff respeitando `Retry-After`,
   fim do kill switch irreversível, e `429` deixa de ser tratado como `401`.
2. **Persistir resultado** — mata a repetição de custo, que é o que
   transformou 18 em 2.
3. **Multi-provedor** — OpenRouter principal, Groq reserva.
4. **Extração no upload + backfill** — tira o OCR do caminho crítico.
5. **Ranqueamento assíncrono + aba de Resultados**.
6. **Status que discrimina** + correção do `.heic` e do `curriculo_nome` NULL.

---

## Pergunta aberta (levantada pelo Grumbal, ainda sem resposta)

**Quantos dos 131 talentos têm currículo anexado?**

Não muda **o que** construir — muda o **tamanho do ganho**. Se forem poucos
(ex.: 12 de 131), o gargalo real do Bruno não é IA nenhuma: é que quase
ninguém anexa currículo, e isso se resolve no **formulário público**, não no
worker. Consulta:

```sql
SELECT count(*) AS total,
       count(curriculo_key) AS com_curriculo,
       count(*) FILTER (WHERE curriculo_key IS NOT NULL AND curriculo_nome IS NULL) AS cv_sem_nome
FROM talento;
```
