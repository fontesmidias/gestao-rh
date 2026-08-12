# Gravação e transcrição de entrevistas — viabilidade e desenho

> Status: **análise de viabilidade, com decisões do Bruno travadas** (2026-08-11,
> party mode). Não implementado. O que estiver em desacordo com o § 3 é
> regressão, não melhoria.

## 1. O pedido

> *"Pensar no módulo de Entrevistas: ter a possibilidade de gravar e gerar a
> transcrição do áudio. Seria possível identificar os interlocutores? Quais
> seriam as tecnologias com e sem IA? Seria um contêiner à parte?"*

## 2. O *job*, antes da tecnologia

O valor não é "ter o áudio" nem "ter uma transcrição perfeita". É:

1. **não perder o que foi dito**, e
2. **não escrever enquanto entrevista** — hoje o entrevistador divide atenção
   entre conduzir e anotar, e quem paga é a qualidade da justificativa que ele
   escreve depois, num documento que assina.

Isso importa porque decide o escopo: **diarização perfeita não é requisito desse
job**. É requisito de um produto que ninguém pediu.

## 3. Decisões do Bruno (travadas)

| Decisão | Valor |
|---|---|
| Processamento | **Fila** (Redis + RQ, que já existe e está ociosa) |
| Onde roda | **Container separado** |
| Modelo | **Self-hosted. Sem API paga.** Biblioteca de mercado ou própria |
| Onde aparece | Módulo de **Arquivo** *e* no **card da entrevista**, para baixar |

> ⚠️ **A decisão "self-hosted, sem API paga" tem motivo: áudio de entrevista não
> sai de casa.** Está registrada aqui porque, sem registro, daqui a seis meses
> alguém "otimiza" trocando por um serviço pago e desfaz a decisão sem saber que
> ela existiu.

## 4. As três camadas, e o que custa cada uma

### 4.1 Gravar — barato, já temos o caminho

`MediaRecorder` no navegador (API nativa, sem biblioteca), upload para o MinIO
pelo caminho de upload que já existe. Formato `audio/webm` (Opus) é o que o
Chrome entrega e é compacto: ~1 MB por 2 minutos.

⚠️ O teto de upload é **configurável no painel** (v2.56) — uma entrevista de 40
minutos passa do padrão. Conferir antes, senão o primeiro uso real falha por
tamanho.

### 4.2 Transcrever — duas famílias

| | Self-hosted (`faster-whisper`) | API paga |
|---|---|---|
| Custo | Zero por minuto; CPU | ~US$ 0,20–0,40/entrevista |
| Dado | **Fica em casa** | Sai do país |
| Velocidade | Minutos de CPU por entrevista | Quase imediato |

**Escolhido: `faster-whisper`** (CTranslate2). Roda em CPU, modelo `small` ou
`medium` dá conta de português. Não precisa de GPU; precisa de RAM e tempo — que
é exatamente o que uma fila resolve.

Alternativa sem IA nenhuma (registrada para descartar com clareza): reconhecimento
por HMM clássico tipo Kaldi/Vosk. **Vosk é viável e leve**, mas a qualidade em
português com áudio de sala é bem inferior à do Whisper, e o esforço de integrar
é o mesmo. Não compensa.

### 4.3 Diarização ("quem falou quando") — **fora da v1**

Padrão de mercado é `pyannote.audio` (exige token do HuggingFace, mais pesado).

**Por que fica de fora:**

- A qualidade despenca com áudio de sala ruim ou de reunião online gravada de um
  lado só, com eco — que é o caso real aqui.
- A taxa de erro de atribuição é alta o bastante para a transcrição afirmar que
  **o candidato** disse algo que **o entrevistador** disse.
- Isso entra numa ficha que a pessoa **assina**. Aí não é ruído: é risco
  jurídico.

Se vier depois, `pyannote` é o candidato — com a ressalva acima registrada.

## 5. Consentimento — a parte que decide se isto pode existir

**Gravação de voz é dado pessoal sob a LGPD**, e há entendimento de que voz é
dado biométrico. Portanto:

- **Consentimento específico e destacado.** Não pode ser enterrado no aceite LGPD
  genérico que o portal já coleta — misturar os dois seria carimbar consentimento
  que ninguém deu (a lição da v2.73, onde o cadastro pelo RH deixa
  `consentimento_lgpd_em` NULO de propósito).
- **Recusável sem custo, e visivelmente sem custo.** Uma entrevista de emprego é
  a conversa mais assimétrica que existe: de um lado quem decide, do outro quem
  precisa do emprego. Se o consentimento aparecer como um checkbox no meio do
  fluxo, a pessoa clica — não porque concordou, mas porque **não sente que pode
  recusar**. A tela precisa dizer que recusar não afeta a avaliação.
- **O entrevistador vê que a pessoa recusou**, para não perguntar de novo.
- **Terceiro estado, nunca travessão**: "não consentiu" ≠ "não temos o dado"
  (regra do creche, v2.27/v2.54).

Sem isso, o que se constrói é teatro de consentimento.

## 6. Por que container à parte

O `faster-whisper` carrega modelo na memória e consome CPU por minutos. Dentro
da API ele competiria com requisição de gente real, e o nginx corta em 60s.

A infra certa **já existe e está subutilizada**: Redis + RQ desde a v1.83, com a
camada `services/fila.py` da v2.00 (*"use `fila.enfileirar` para qualquer
trabalho que possa passar de ~30s"*). Transcrição é o caso de uso canônico.

⚠️ **Worker novo precisa entrar nos DOIS arquivos de deploy** — `docker-compose.base.yml`
**e** `portainer-stack.yml`. A armadilha da v2.66: worker que está só num deles
**não roda em produção**, e não gera erro — gera silêncio.

## 7. Onde o resultado aparece

Decisão do Bruno: **nos dois lugares**.

- **Card da entrevista** — quem conduziu baixa a transcrição do trabalho dele.
- **Módulo de Arquivo** — onde documentos se procuram depois.

⚠️ **A transcrição NÃO entra no dossiê de admissão.** O `services/dossie.py` varre
`SolicitacaoAssinatura` **sem filtrar `origem`**, então qualquer fluxo de
assinatura novo entra no dossiê **por padrão** — foi por isso que a assinatura da
ficha de entrevista mora em tabela própria (v2.67, § 15.4: *"no dossiê de
admissão não"*). O dossiê circula: vai para o cliente e para a pasta física.
Transcrição de entrevista lá dentro seria vazamento silencioso — uma página a
mais que ninguém confere.

## 8. Estados que precisam existir (nada some em silêncio)

Mesma regra do Match (v2.00): *"ninguém some em silêncio"*. A transcrição precisa
de estado gravado e visível para cada desfecho:

- `aguardando` — na fila;
- `processando`;
- `pronta`;
- `falhou` — **com o motivo**;
- `sem_consentimento` — não foi gravada, e por quê;
- `audio_inaudivel` — gravou, não deu para transcrever.

Ausência de transcrição sem motivo faria o entrevistador achar que o sistema
perdeu o trabalho dele.

## 9. Ordem de execução sugerida

1. **Consentimento e telas primeiro** — decidir e desenhar antes de escrever
   código de áudio. Sem isso vira a v2.74 (promessa na tela sem rota atrás).
2. Gravar + guardar (sem transcrever). Já entrega "não perder o que foi dito".
3. Container `transcricao` + worker na fila, com `faster-whisper`.
4. Exibição no card e no Arquivo, com os estados do § 8.
5. Diarização: **só depois**, e só se o § 4.3 for reavaliado com áudio real.

## 10. Divergência registrada

A sala não fechou consenso sobre a **prioridade** deste módulo, e isso fica
registrado em vez de alisado:

- **Contra priorizar agora**: é o item mais caro e o de menor retorno imediato
  dos três da leva; deveria ficar como estudo.
- **A favor de decidir agora**: o consentimento e o desenho de tela precisam ser
  resolvidos **antes** de alguém escrever código, senão vira promessa na tela sem
  rota atrás (v2.74).

Resolução adotada: **decide agora, constrói depois** — que é o que este documento
é.
