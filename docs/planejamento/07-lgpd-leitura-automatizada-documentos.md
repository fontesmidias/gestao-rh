<!-- Base legal e registro de tratamento para a leitura automatizada de
documentos (Onda 0/B). MINUTA TECNICA redigida em 2026-07-22 a pedido do
Bruno. NAO e parecer juridico: precisa de revisao e assinatura de quem
responde pela Green House antes de valer. Os textos de aviso ao titular ja
estao prontos para colar na interface. -->

# LGPD — leitura automatizada de documentos

> **Status: APROVADO pelo Bruno em 2026-07-22** — ele informou que a
> verificação jurídica foi feita e mandou considerar validado. As bases legais
> e o registro de tratamento abaixo passam a valer como decisão da Green House.
>
> Permanece a trava **técnica** (não jurídica) do § 4: enquanto o Zero Data
> Retention não estiver aprovado pela Mistral, o tipo `saude` fica barrado no
> código. Isso protege contra a retenção padrão de 30 dias no provedor — é
> engenharia, e sai sozinha quando o ZDR entrar.

## 1. O que está sendo tratado

O colaborador envia documentos pelo portal; o sistema os submete a um serviço
de leitura automatizada (OCR/IA) que **extrai campos** (número, datas, nome,
órgão emissor) para **pré-preencher** o formulário. A pessoa confere e confirma
antes de qualquer gravação.

| Documento | Categoria LGPD | Leitura automatizada |
|---|---|---|
| RG / CPF / CNH | Dado pessoal comum (art. 5º, I) | Sim |
| Certificado de formação / reciclagem | Dado pessoal comum | Sim |
| Atestado de Saúde Ocupacional (ASO) | **Sensível — saúde** (art. 5º, II) | Sim, **condicionada** (§ 4) |

## 2. Base legal

### 2.1. Documentos comuns (RG, CPF, CNH, certificados)

**Art. 7º, V — execução de contrato**: são documentos necessários à relação de
trabalho e à comprovação de habilitação profissional exigida do posto.

Subsidiariamente, **art. 7º, II — cumprimento de obrigação legal ou
regulatória** (documentação de admissão e de qualificação obrigatória).

### 2.2. Atestado de Saúde Ocupacional — dado sensível

Dado sensível **não** admite "legítimo interesse". A base correta é o **art. 11,
II**, e há duas alíneas aplicáveis, que se somam:

- **art. 11, II, "a" — cumprimento de obrigação legal ou regulatória pelo
  controlador.** O ASO é exigido pela **NR-7 (PCMSO)** e a aptidão do brigadista
  é exigida pela **NR-23** e pela normativa do corpo de bombeiros para o curso
  de formação/reciclagem. A empresa não pede o ASO porque quer: é obrigada.
- **art. 11, II, "f" — tutela da saúde, em procedimento realizado por
  profissionais de saúde.** Aplica-se ao encaminhamento à clínica (Multicursos),
  que é quem avalia a aptidão.

> **Consentimento NÃO é a base adequada aqui.** Em relação de emprego o
> consentimento é viciado por assimetria de poder (o empregado não pode dizer
> "não" com liberdade). Usar consentimento como base legal para ASO é um erro
> comum e frágil — a obrigação legal é a base sólida.

**Finalidade específica e declarada:** montar o dossiê exigido pela entidade
formadora para matrícula no curso de formação/reciclagem de brigada, e controlar
a validade da certificação. **Não** é para avaliar desempenho, nem para decisão
sobre promoção, nem para qualquer outra finalidade.

## 3. Princípios que restringem a implementação

Estes não são conselhos — são o art. 6º da LGPD traduzido em regra de código.

| Princípio | Como aparece no sistema |
|---|---|
| **Finalidade** (I) | O ASO só é usado para o dossiê da clínica e o controle de validade. **Nunca** entra no módulo de avaliação de desempenho. |
| **Necessidade** (III) | Extrai-se **apenas** o que o dossiê exige: aptidão (apto/inapto), data do exame e validade. **Não** se extrai diagnóstico, CID, exame ou queixa. |
| **Transparência** (VI) | Aviso na tela de upload (§ 5) e informação de que houve leitura automatizada. |
| **Segurança** (VII) | Documento original só no MinIO da VPS; envio ao provedor por HTTPS; chave na config dinâmica, nunca em log. |
| **Não discriminação** (IX) | O resultado do ASO **não** alimenta ranking, nota ou qualquer decisão automatizada. |
| **Responsabilização** (X) | Log de auditoria de toda leitura de documento sensível: quem, quando, tipo, hash. Nunca o conteúdo. |

## 4. Condições técnicas obrigatórias (operador: Mistral)

Verificado na documentação oficial em 2026-07-22:

1. **Plano Scale + Zero Data Retention (ZDR) aprovado.** Sem ZDR, a retenção
   padrão é de **30 dias** para monitoramento de abuso. Reter dado de saúde por
   30 dias num terceiro, sem necessidade, viola o princípio da necessidade.
   O ZDR cobre `/v1/ocr` (endpoint stateless), mas **só existe no plano Scale** e
   **só mediante pedido aprovado** caso a caso.
2. **DPA (Data Processing Addendum) assinado** — formaliza a Mistral como
   **operadora** (art. 39) e a Green House como **controladora**.
3. **Proibido o tier gratuito** para qualquer documento deste módulo: o tier
   *Experiment* usa entradas e saídas para treinamento por padrão.
4. **Roteamento por sensibilidade no código**, não em política: enquanto o ZDR
   não estiver aprovado, o tipo `saude` é **barrado na origem** e os demais
   documentos seguem funcionando.
5. **Nada é persistido no provedor:** entra, extrai campo, sai. O original fica
   no MinIO.
6. **A IA propõe, o humano confirma.** Nenhuma gravação automática — o que
   também afasta a discussão de "decisão automatizada" do art. 20.

## 5. Textos para a interface (prontos para colar)

### 5.1. Tela de upload — documento comum

> 🔎 **Leitura automática:** para você não precisar digitar, lemos o documento
> automaticamente e preenchemos os campos. **Confira e corrija** o que estiver
> errado antes de continuar — o que vale é o que você confirmar.

### 5.2. Tela de upload — atestado de saúde

> 🔒 **Documento de saúde.** Este atestado é exigido pela clínica para a sua
> matrícula no curso e é usado **somente** para isso e para controlar a validade
> da sua certificação. Ele **não** é usado na sua avaliação de desempenho.
>
> Para agilizar, lemos automaticamente apenas **a data do exame e a validade** —
> nenhum diagnóstico é extraído ou armazenado pelo sistema. Confira os campos
> antes de confirmar.

### 5.3. Aviso de privacidade — trecho a acrescentar

> **Leitura automatizada de documentos.** Os documentos que você envia passam
> por leitura automatizada (OCR com inteligência artificial) com a única
> finalidade de pré-preencher os campos do formulário, poupando digitação. O
> processamento é feito por operador contratado sob acordo de tratamento de
> dados, sem retenção do conteúdo e sem uso para treinamento de modelos. O
> arquivo original permanece armazenado nos sistemas da Green House. **Nenhuma
> decisão sobre você é tomada automaticamente:** o preenchimento é sempre
> conferido e confirmado por você e, quando for o caso, validado pelo RH.

## 6. Registro de operações de tratamento (art. 37)

| Campo | Conteúdo |
|---|---|
| **Controlador** | Green House (Brasília/DF) |
| **Operador** | Mistral AI (França/UE) — leitura automatizada, sob DPA |
| **Categorias de titulares** | Colaboradores e candidatos |
| **Categorias de dados** | Identificação (nome, RG, CPF, CNH); qualificação (certificados); **saúde** (aptidão e validade do ASO) |
| **Finalidade** | Pré-preenchimento de formulário; montagem de dossiê para entidade formadora; controle de validade de certificação obrigatória |
| **Base legal** | Art. 7º, II e V (comuns); **art. 11, II, "a" e "f"** (saúde) |
| **Transferência internacional** | Sim — provedor na UE. Art. 33, II (país com grau de proteção adequado / cláusulas contratuais no DPA) |
| **Retenção no operador** | **Zero** (ZDR contratado) |
| **Retenção no controlador** | Enquanto durar o vínculo + prazo legal aplicável; expurgo pela lixeira (`services/lixeira.py`) |
| **Medidas de segurança** | HTTPS; chave em config dinâmica fora do código; log de auditoria com hash e sem conteúdo; acesso do RH autenticado; portal do colaborador com 2FA/KBA |

## 7. Pendências para a revisão jurídica

1. Assinar o **DPA da Mistral** e arquivar (o registro acima presume assinado).
2. Confirmar o **prazo de retenção** do ASO no controlador — a NR-7 tem prazo
   próprio de guarda do PCMSO, que pode ser maior que o do vínculo.
3. Avaliar se o **encarregado (DPO)** já está formalmente designado e publicado
   (art. 41) — o aviso de privacidade deve trazer o canal de contato dele.
4. Decidir se o ASO fica no MinIO da VPS ou se, por ser sensível, merece
   **retenção mais curta** que os demais documentos (o expurgo já é
   configurável).
5. Verificar se o contrato com a **Multicursos** prevê o compartilhamento (ela
   também vira operadora ao receber o dossiê).

---

<!-- Redigido em 2026-07-22. Fonte das condicoes da Mistral: docs.mistral.ai
(privacy-data-controls) e help.mistral.ai (artigo 347612 sobre ZDR),
consultados na mesma data. -->
