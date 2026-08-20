# 🌱 Portal de RH — admissão, documentos e assinaturas

**Sistema de RH para empresas de terceirização: admissão digital sem papel, base de colaboradores, testes comportamentais, benefícios, geração de documentos e assinatura eletrônica com vários signatários — tudo auditável, do convite ao dossiê.**

*Self-hosted HR platform for Brazilian outsourcing companies: passwordless onboarding, workforce base, behavioral tests, document templates, multi-party electronic signatures (Brazilian Law 14.063/2020) with public QR verification, and a full audit trail. [English summary below](#-english-summary).*

[![CI](https://github.com/fontesmidias/gestao-rh/actions/workflows/ci.yml/badge.svg)](https://github.com/fontesmidias/gestao-rh/actions/workflows/ci.yml)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green.svg)](LICENSE)

> **Marca configurável.** O sistema nasceu para a Green House (Brasília/DF), mas o nome, a razão social, o CNPJ, o endereço, a logo e o favicon da empresa são **editáveis pelo painel** (Configurações → Identidade visual). Os valores da Green House são apenas o padrão inicial.

---

## 😫 A dor que deu origem a isto

O processo anterior era um Microsoft Forms de **50 perguntas** costurado a fluxos de Power Automate: o candidato preenchia tudo de uma vez (sem salvar), mandava documentos por WhatsApp e e-mail, o RH imprimia fichas, colhia assinaturas à caneta, conferia papel por papel e montava o dossiê à mão. Resultado: **semanas** de ida e volta, documentos perdidos, retrabalho — para um público que, em grande parte, só tem o celular como computador.

O que começou como um "portal de admissão" cresceu para uma **plataforma de RH** completa da operação de terceirização.

## ✨ O que o sistema faz

### Admissão (candidato — mobile-first, sem senha)
- **Link mágico** sem senha; retorno por **CPF + perguntas de verificação** (estilo TSE) para quem perde o link
- **Wizard de 6 etapas com autosave por campo** — fecha o navegador e continua depois; máscara de datas, busca de CEP, validação de CPF, nome social (Decreto 8.727/2016)
- **Câmera guiada**: moldura por tipo de documento, semáforo de luz/foco, captura frente e verso, conferência antes do envio — sempre com a alternativa de enviar arquivo
- **OCR** (Tesseract local, opcionalmente Mistral com chave própria) que *sugere* o preenchimento a partir do RG/CNH/CPF/comprovante — só com consentimento, nunca sobrescrevendo o que foi digitado
- **"Ver o que enviei"**: cada documento enviado abre **na própria tela**, mostrando o arquivo *como a pessoa mandou* (todas as partes — frente, verso, páginas), com o PDF que o RH recebe a um toque de distância
- **Testes comportamentais** antes do cadastro: inventário DISC e teste situacional, com timer e telemetria; o resultado é restrito ao RH

### Base de colaboradores e postos (RH)
- Candidato e colaborador são o **mesmo registro** — em admissão (`situação` nula), ativo ou desligado
- **Importação idempotente** da base do Tirvu (.xlsx) por CPF; postos de serviço com documentos específicos por posto/regime (INFRAERO, Presidência, intermitente)
- **De-para de lotações**: a lotação vem abreviada no Tirvu ("INEP ADM") e o posto tem nome completo — o sistema ordena os candidatos por semelhança **de palavra**, mostra quantas pessoas dependem de cada decisão, e onde há empate real deixa a escolha em branco de propósito
- **Vínculo em massa**: a mesma planilha de Colaboradores preenche jornada, cargo, posto e PCD de mil pessoas de uma vez — quem já tem valor diferente **nunca é sobrescrito** (vira lista de decisão), e o que não casa aparece com quantas pessoas dependem
- **Cargos e jornadas do Tirvu por upload de .txt** (o Tirvu não exporta: o RH copia a tela, salva no Bloco de Notas e sobe o arquivo) — com ID, CBO, escala e tratamento; o sistema propõe o de-para e separa o que é ambíguo para o RH decidir, nunca funde sozinho
- Dashboard, filtros e **exportação Excel** com uma linha por colaborador e todas as respostas
- **Exportação para os sistemas de folha**, fiel ao layout de cada um: **Tirvu** (28 colunas, aba `Plan1`, sem autofiltro — ele recusa a "decoração") e **Dexion** (97 colunas A→CS, cabeçalho de 4 linhas, datas em serial do Excel e `autoFilter`, que o outro rejeita). Cada um tem gerador próprio: os dois só se parecem de longe, e copiar um produziria um arquivo que *parece* certo. Antes do download, uma **pré-checagem diz quem tem campo faltando, com nome e motivo** — no Dexion, código do eSocial errado não dá erro na importação: entra limpo e sai errado na declaração meses depois

### Atendimento presencial
- Para quem chega com os documentos na mão e não tem prática com tecnologia: o RH abre o **mesmo formulário** e preenche com a pessoa ao lado. O que muda não é o fluxo — é o **registro**: a assinatura continua sendo dela (código no e-mail dela), e o manifesto do documento passa a declarar *"colhida presencialmente, em atendimento assistido por [nome], na presença do titular"*, em vez de afirmar que ela assinou sozinha na plataforma

### Documentos e assinaturas
- **Ficha de integração por regime**: o documento de boas-vindas (dados, VT, VA, conta salário, ponto pelo Tirvu+, prazos de assinatura e normativos) existe para **efetivo e intermitente**. A diferença é o ciclo de pagamento dos benefícios — o efetivo apura **do dia 1 ao dia 30**; o intermitente, **semanalmente**. Só vai ao colaborador depois que o RH libera
- **Modelos de documento** no papel timbrado, com variáveis (`{{nome}}`, `{{cargo}}`…), prévia, envio pontual e predefinições (Ofício, Comunicado, Contrato, Declaração). A variável é **escolhida numa lista com busca e entra na posição do cursor**, nos modelos e nos textos de e-mail — digitá-la à mão erra em silêncio: um `{{nome_socal}}` sem o "i" não casa com nada, não dá erro e sai impresso no PDF que a pessoa assina
- **Assinatura eletrônica simples** (Lei 14.063/2020, art. 4º, I): código de uso único por e-mail, manifesto de evidências no PDF (hash SHA-256, IP, dispositivo, data) e **verificador público por QR code**
- **Multi-signatário em ordem de papéis**: um documento pode exigir a assinatura do colaborador, de alguém do RH (assina logado) e/ou de um terceiro externo (link próprio + código), em sequência — o PDF final consolida todas as assinaturas
- **Assinatura da equipe por autorização prévia**: um representante autoriza uma vez (ato de vontade datado), e sua assinatura passa a constar nos documentos daquele modelo — sem carimbo falso
- **Ordem das fichas configurável** · **re-assinatura granular** quando um dado muda (só as fichas afetadas voltam) · **central de assinaturas** com dashboard de todos os candidatos

### Portal do colaborador (`/meu`) — a vida na empresa, não só a admissão
- **Uma porta para tudo que é da pessoa**: cursos, certificados, pendências e avaliações, com o mesmo gate sem senha do resto (CPF → 2FA por e-mail; sem e-mail, perguntas de verificação que funcionam até para quem foi importado do Tirvu e nunca preencheu ficha)
- A home é a **lista de pendências dela** — o que vence, o que o RH devolveu — não um menu

### Desenvolvimento e reciclagem de brigadistas
- **Cadastro de Desenvolvimento**: o colaborador registra cursos, treinamentos e certificações ao longo do vínculo; tipos configuráveis pelo RH com validade, criticidade e cargos aplicáveis, e prazo por posto/cargo. A IA pré-preenche a partir do documento; a pessoa confere
- **Fila de validação** com aprovação em lote para o caso fácil — documento crítico (brigada, NR) nunca entra no lote e é conferido um a um
- **Controle de reciclagem**: quem tem certificação crítica vencendo, com **aviso automático 90 dias antes**, e montagem do e-mail de matrícula à entidade formadora (individual ou em grupo, com o dossiê de cada um em PDF único)

### Avaliação de desempenho (a Cartilha do Avaliador, digitalizada)
- **Fatos Observados**: a liderança registra na hora o que a pessoa fez, com fato e impacto — antídoto do "esqueci o que ela fez na hora de avaliar". **O colaborador vê os fatos sobre ele, mas nunca quem registrou**
- **Formulário 360** (11 seções da cartilha) com os fatos e a frequência do período ao lado; vertical (liderança, identificada) e horizontal (pares, **anônima e agregada**). Uma máquina de estados **não deixa pular a conversa de feedback presencial**
- **Direito de resposta** do colaborador (manifestação, com prazo), **radar** de competências + **timeline** das médias, e **calibração** que informa ao homologador quando um avaliador é mais generoso/rigoroso que os demais — sem alterar nota
- **Frequência do Tirvu** importada por planilha entra como **contexto**, nunca nota; registro incompleto (esqueceu de bater a saída) jamais é contado como falta

### Recrutamento e seleção
- **Banco de Talentos**: formulário público (substituiu o Microsoft Forms) com **currículo obrigatório** — arquivo ou foto das páginas, avisado já no primeiro passo —, importação idempotente da planilha do Forms e consentimento LGPD obrigatório. O RH também **cadastra à mão** pelo painel, e ali o currículo pode faltar **com justificativa** (indicação, contato por telefone), que fica na ficha e na auditoria. Nesse caso o consentimento **não é fingido**: fica registrado quem cadastrou, e a ficha diz "sem aceite" em vez de simular um que não houve. Quem já está cadastrado e se cadastra de novo **atualiza o próprio registro**, sem duplicar — e a resposta é idêntica à de um cadastro novo, porque revelar "já existe" numa rota pública a transformaria numa sonda para descobrir quem está na base. No painel, duplicata **avisa dizendo quem já existe**, nunca funde sozinha
- **Match de Vagas**: o RH cadastra a vaga e o sistema ranqueia os talentos por aderência — filtro estruturado local primeiro (grátis), currículo lido por IA depois. **A IA nunca decide sozinha**: devolve nota e justificativa, o RH convoca. O ranqueamento é **assíncrono** (enfileirado), o texto do currículo é extraído **uma vez** no upload e a análise é reaproveitada por (vaga, talento)
- **Currículo é tratado como entrada hostil**: é upload público de gente desconhecida cujo texto vai para dentro de um prompt. Cinco camadas anti-prompt-injection e o suspeito aparece marcado **"⚠️ suspeito"** no ranking — **nunca filtrado em silêncio**, porque ranking adulterado parece igual a um legítimo. CPF/RG/telefone/e-mail são removidos antes do envio à IA
- **Ninguém some sem explicação**: sem currículo, ilegível, aguardando IA e erro são resultados **gravados e exibidos com o motivo** — não ausência
- **Provas por cargo**: banco de provas configurável pelo RH (objetivas com correção automática e discursivas pontuadas), aplicação por link avulso com timer, aleatorização por participante e **banco de itens** reutilizável. O gabarito nunca vai ao público
- **Teste já respondido é aproveitado**: quem fez DISC, situacional ou prova antes de virar candidato não refaz — e fica registrado se a identidade foi deduzida pelo sistema ou afirmada por uma pessoa, porque o link avulso é anônimo e homônimo existe
- **Entrevistas**: o degrau entre "olhei o currículo" e "mandei o convite", que antes não deixava rastro. Duas fichas de natureza diferente — **triagem** (checagem de viabilidade por telefone, sem nota) e **entrevista** (4 competências ancoradas, escala 1–4 sem ponto médio, **justificativa obrigatória em cada nota**). O roteiro é fixo e pré-aprovado: campo de pergunta livre é risco jurídico (Lei 9.029/95), roteiro escrito é defesa da empresa
- **A entrevista pergunta, nunca conclui**: passou da data e ninguém preencheu, vira **pendência que cobra** — jamais "não compareceu" automático, porque silêncio não é falta. Seguro-desemprego é registrado na triagem e **nunca é critério de exclusão**
- **Comparar e lembrar**: na tela da vaga, as 4 notas de cada entrevistado lado a lado (é como se escolhe entre três candidatos e como se aloca numa vaga com várias posições); na ficha da pessoa, o histórico que atravessa talento↔candidato. Aos 180 dias a entrevista **é arquivada, não apagada** — sai da vista e das métricas, a memória continua acessível
- **Roteiros por cargo, aprovados antes de usar** (Configurações → Roteiros de entrevista): o RH monta roteiros próprios por cargo e senioridade — o mais específico vence, e cargo sem roteiro usa o padrão. O roteiro nasce **rascunho** e só pode ser usado depois de **publicado**; é isso que permite dizer que ele foi aprovado *antes* de ser usado. Editar um roteiro publicado gera a versão seguinte e **não altera a entrevista já feita**, que guarda o instrumento com que foi conduzida
- **Convite e lembrete**: a entrevista pode ser **presencial** (endereço) ou **online** (link colado pelo RH — sem link não se marca, porque o convite sairia sem dizer por onde entrar). Sai e-mail ao marcar e lembrete na véspera, com **convite de calendário** que o Outlook *atualiza* na remarcação e *remove* no cancelamento. Quem não tem e-mail no cadastro fica com o lembrete desligado **e a tela diz por quê**
- **Endereço de recrutamento** (Configurações → E-mail e integrações): o convite e o lembrete podem sair de um endereço próprio, em vez da caixa de login. No **Microsoft 365** isso só vale depois que o administrador liberar a permissão **"Enviar como" (Send As)** daquele endereço para a conta conectada — enquanto não liberar, os convites **continuam saindo normalmente** pelo endereço de sempre e **o sistema avisa na tela** o que falta fazer. O e-mail nunca deixa de sair porque o tenant não foi configurado
- **Reaproveitar quem já conversou**: ao fechar uma vaga, o sistema mostra quem foi entrevistado e **propõe** uma tag do mini-CRM para reaproveitá-los em outras vagas — sugerida a partir do cargo, aplicada só depois que o RH confirma. As tags já filtram no Banco de Talentos
- **A ficha vira documento — e é assinada por quem conduziu**: ficha de entrevista, ficha de triagem e roteiro publicado entram no catálogo de documentos do sistema, com prévia em PDF e download. A ficha preenchida é **assinável pelo RH que conduziu**, logado, com a senha da própria sessão (o entrevistado não assina). Ficha incompleta **não** vira documento, e roteiro em rascunho também não — o documento serve para provar que o roteiro foi aprovado *antes* de ser usado
- **A ficha NÃO entra no dossiê de admissão**: ela vive no Arquivo e na ficha da pessoa, os dois lugares de acesso exclusivo do RH. O dossiê **circula** — vai ao cliente, à pasta física, a quem pedir — e nota de seleção com justificativa escrita é dado sensível sobre a pessoa. A separação é estrutural (tabela própria, fora do que o dossiê lê), não uma lembrança
- **Perguntas de triagem editáveis, sem virar avaliação**: a triagem entra no mesmo catálogo de roteiros, com a mesma aprovação rascunho→publicado, e **continua sem nota, sem competência e sem âncora** — o sistema recusa, nomeando o campo, quem tentar pôr qualquer um dos três numa triagem. Cada natureza tem o seu roteiro padrão
- **Mini-CRM**: anotações e tags que acompanham a **pessoa** de talento → candidato → efetivo → desligado, com autor snapshot e anexo
- **Minutário de Mensagens**: modelos de mensagem e composição assistida por IA a partir dos campos da **vaga** — o texto volta sempre editável e nunca é enviado sozinho

### Benefícios, testes, arquivo
- **Reembolso-Creche** (IN SEGES/MGI 147/2026): elegibilidade e **vigência** por posto (o aditivo de cada contrato tem data de início), link público de levantamento com 2FA (ou perguntas de verificação para quem não tem e-mail), assinatura do requerimento e o ciclo de decisão do RH — aprovar, devolver para correção, indeferir por criança, "não faço jus", suspender/encerrar — com aviso ao colaborador em cada passo. O benefício aparece também **nas telas de Colaboradores e Admissões** — quem está com comprovante pendente, e quem vai para posto elegível sem ter informado criança —, em vez de viver só na tela do Creche. Depois de ativo, entra o **ciclo mensal**: todo mês, um comprovante **por criança** — nota fiscal se a creche for PJ, declaração de quitação se o cuidador for PF —, com corte no dia configurável (padrão 25), lembretes automáticos com a antecedência que o RH escolhe, envio pelo colaborador **ou pelo RH**, várias folhas por documento e o valor do posto valendo como **teto** do reembolso
- **Decisão por criança, um requerimento só**: com mais de um filho, o RH defere uns e indefere outros na própria linha, com o motivo. O valor do reembolso é por criança deferida e acompanha as decisões; o requerimento que o colaborador assina lista as contempladas e registra as negadas em seção própria — antes, negar um filho exigia removê-lo do cadastro, e a prova de que fora analisado sumia junto
- **Quem faz jus, e até quando**: aba própria com a data em que cada criança sai da idade, quantos dias faltam e quem já saiu — o fechamento mensal do DP deixa de ser constatação depois do fato e vira previsão. Tudo derivado da data de nascimento, sem coleta nova. A idade tem **quatro estados**, não dois: na idade, fora da idade, data ilegível e **data implausível** (nascimento de adulto no campo do filho, que já apareceu em campo) — os dois últimos são "conferir", nunca negativa, e ficam fora do alarme de risco de glosa
- **Central de testes**: dashboard de todos os testes (admissão + testagem avulsa), reset, relatório de comportamento; links de testagem anônima onde a pessoa vê o próprio resultado
- **Arquivo/backup**: inventário com filtros, download individual e **backup em lote** (ZIP por posto/pessoa + planilha XLSX), auditado
- **DashPlanilha**: componente único de lista do RH (ordenação, filtro por coluna, seleção em massa, colunas configuráveis, export CSV e cards-métrica clicáveis) — o padrão de todas as telas de lista

### O que o RH edita sem depender de deploy
- **Textos de todos os e-mails**, com preview, histórico append-only de quem mudou o quê e restauração. O **template é apresentação, nunca decisão**: os e-mails que enumeram documentos recebem a lista pronta como `{{lista}}` — a regra do que entra continua no código. Variável obrigatória é validada no salvamento (um e-mail de acesso sem `{{codigo}}` sai bonito e vazio, e ninguém mais entra no sistema)
- **Quem recebe cada aviso interno** (matriz evento × destinatários) — nunca a caixa de login, que é pessoal
- **Catálogo dos documentos do sistema**: os 11 documentos da admissão com amostra em PDF de verdade, download e "criar modelo a partir deste" nos de texto corrido. Os geradores oficiais **não são substituídos** — o hash do ato de assinatura é calculado sobre o PDF gerado, então trocá-los faria os manifestos já emitidos apontarem para um hash que não se reproduz
- **Uniformes**: lista com as medidas informadas no wizard, na tela e com export CSV. O e-mail ao operacional diz só que há novidade — ficha de pessoal não circula por caixa de e-mail
- **Credenciais de automação**: token de MÁQUINA para integrações consultarem o portal no lugar da senha de uma pessoa — o segredo aparece **uma única vez** (o banco guarda só o resumo criptográfico), é **revogável a qualquer momento**, e revogar **marca em vez de apagar**: a linha é a prova de que a credencial existiu e de quando deixou de valer
- **Central de Importações**, tags, tipos de certificado, prazos por posto/cargo, identidade visual e provedor de e-mail

### Telemetria de uso — enxergar o que acontece no aparelho das pessoas
- **Erros de tela registrados**: quando algo quebra no navegador de um candidato, o RH vê — antes, esse erro morria lá e o servidor registrava um `200` tranquilo, porque do lado dele tinha dado tudo certo
- **Onde as pessoas travam**: documento reenviado, arquivo recusado antes de sair do aparelho, formulário que não deixou avançar, link vencido. Quem desiste não reclama — simplesmente não volta, e sem isto era invisível
- **Individualizada na ficha da pessoa** (candidato, colaborador, talento): responde *"não consigo enviar meus documentos"* com fato, não com suposição
- **Aba própria** (Configurações → 📈 Telemetria) com os erros **agrupados** por mensagem — 300 ocorrências do mesmo erro são um problema, não trezentos — e as páginas lentas por **mediana**, que é o que a maioria realmente espera
- **O sistema avisa você** — não espera alguém abrir a tela: a cada 15 minutos ele verifica e manda e-mail quando um erro **novo** aparece, quando um erro conhecido dispara de volume, quando muita gente trava no mesmo ponto ou quando uma página fica lenta. As regras e os limites são editáveis no painel, e quem recebe sai da mesma matriz de Avisos internos
- **Com nome e link para a ficha**: a lista de eventos diz de *quem* é cada linha e abre a pessoa em um clique — quem não se identificou continua anônimo
- **Export de jornada** em CSV cronológico (`user_id,event,timestamp`), para analisar por onde as pessoas passam antes de concluir — ou de desistir — em qualquer ferramenta de análise de caminho, sem nada instalado no servidor
- **Retenção configurável** (padrão 1 ano), expurgo diário automático e limpeza por intervalo de datas
- **Minimizada por desenho**: nada do que a pessoa digita, IP truncado (`191.180.x.x`) e token do link mágico mascarado — ele é credencial de acesso
- **Logs que permitem investigar**: cada linha traz o identificador da requisição e quem estava agindo, então dá para pegar um erro e ver a sequência inteira — inclusive o que veio antes dele; e-mails registram se saíram ou não, o storage acusa o que está lento, e a hora é sempre a de Brasília

### Experiência de uso e acessibilidade
- **Tour guiado** na primeira visita — no wizard do candidato e no painel do RH (17 telas em 6 grupos), sempre disponível para rever
- **Glossário embutido**: um `?` ao lado dos termos de negócio (*homologar*, *fato observado*, *repactuação*, *calibração*…) explica a **consequência**, não a palavra — e cita a norma quando ela existe
- **Contraste verificado por medição**, não a olho: todo texto passa no mínimo AA da WCAG (4,5:1) **nos dois temas**, conferido no navegador com a folha de estilo real
- **Sistema de design com guarda-corpo automático** ([`08-sistema-de-design.md`](docs/planejamento/08-sistema-de-design.md) + `test_design_system.py`, que roda no CI): classe ou token que não existe, tabela que estoura a tela e remendo inline reprovam antes do merge
- Nada estoura a tela na horizontal (**68 combinações tela × largura verificadas**) · foco visível para navegação por teclado · botão só com ícone tem nome acessível

### Transversal
- **Trilha de auditoria** de tudo (quem, quando, antes → depois) e **hash SHA-256 de todo arquivo antes de qualquer exclusão**
- **Lixeira universal** com restauração e retenção configurável · expurgo LGPD automático · rate limiting em login/2FA
- E-mail por **Microsoft 365 (Graph)**, **Google (Gmail API)**, webhook do Power Automate ou SMTP — configurados pelo painel
- **Nome padronizado em todo download**: `MATRÍCULA - NOME - DOCUMENTO`, caixa alta e sem acento — o cabeçalho HTTP só carrega ASCII com segurança, e a pasta física do RH é toda em caixa alta. Vale para os módulos existentes e os novos
- **Trava anti-duplo-clique** (idempotência no servidor) · tema claro/escuro · **identidade visual da empresa configurável**

## 🏗️ Arquitetura

```
React/Vite (SPA)  ──►  nginx  ──►  FastAPI (Python 3.12)
                                     ├── PostgreSQL 16 (Alembic: migrations automáticas no start)
                                     ├── MinIO (arquivos, S3-compatível)
                                     ├── Redis + RQ (workers: expurgo LGPD, expiração de roteiros,
                                     │               lembrete do comprovante mensal do creche)
                                     └── SMTP / Graph API / Gmail API
```

- **Backend:** FastAPI · SQLAlchemy 2 · Alembic · fpdf2/pypdf (PDFs) · pytesseract + Mistral OCR (leitura de documentos, roteada por sensibilidade LGPD) · qrcode · openpyxl (planilhas do Tirvu lidas por zip+XML, que o openpyxl não aguenta)
- **Frontend:** React 18 · Vite (sem TypeScript) · CSS próprio, sem CDN · tema claro/escuro
- **Infra:** Docker Compose (variantes IP direto / Traefik / certbot) · imagens no GHCR por CI · Playwright E2E contra a stack completa

Estrutura do código: `backend/app/` (`api/` rotas, `models/` SQLAlchemy, `services/` regra de negócio, `workers/` tarefas agendadas); `frontend/src/` (`candidato/` wizard público, `rh/` painel, `api.js` chamadas, `styles.css` CSS único).

## 🚀 Como rodar

### Portainer (recomendado na VPS) — arquivo único, sem build
1. Portainer → *Stacks* → *Add stack* → cole [deploy/portainer-stack.yml](deploy/portainer-stack.yml).
2. Defina as variáveis de ambiente na tela do Portainer (o modo avançado aceita colar o `.env`).

As imagens (`ghcr.io/fontesmidias/gestao-rh-api|frontend`) são **públicas**, publicadas pelo CI a cada push na `main` e a cada tag `v*`.

### Docker Compose (a partir do código-fonte)

```bash
cp .env.example .env   # edite: senhas, SMTP, FRONTEND_PORT

# Local / VPS sem domínio (sem HTTPS — apenas validação):
docker compose --env-file .env -f deploy/docker-compose.base.yml -f deploy/docker-compose.ip.yml up -d --build

# VPS com domínio (Traefik, TLS automático):
docker compose --env-file .env -f deploy/docker-compose.base.yml -f deploy/docker-compose.traefik.yml up -d --build

# VPS com certbot/nginx existentes no host:
docker compose --env-file .env -f deploy/docker-compose.base.yml -f deploy/docker-compose.certbot.yml up -d --build
```

> Use sempre `--env-file .env` (os arquivos compose ficam em `deploy/`, e a interpolação lê o `.env` do diretório do primeiro `-f`). Acesse `http://IP:FRONTEND_PORT` — painel do RH em `/rh`. Na primeira vez, o painel abre um **cadastro guiado** que cria o administrador (nome, e-mail e senha) — não é preciso definir credencial em arquivo nenhum. Para instalação automatizada, `RH_ADMIN_EMAIL`/`RH_ADMIN_PASSWORD` no `.env` continuam funcionando e dispensam a tela.

### Desenvolvimento e testes

```bash
cd backend
PYTHONPATH=. .venv/Scripts/python.exe -m alembic upgrade head        # migrations
PYTHONPATH=. .venv/Scripts/python.exe tests/smoke_test.py            # smoke ponta a ponta (precisa dos containers de teste)
cd ../frontend && npm run build                                     # valida JSX/CSS
```

O smoke test sobe contra Postgres + MinIO efêmeros (ver `CLAUDE.md` para os containers de teste).

### Atualização e rollback (sem perda de dados)

- **Atualizar:** `git pull` + o mesmo `up -d --build` (ou *Re-pull image* no Portainer). As migrations rodam sozinhas no start e preservam os volumes `postgres-data` e `minio-data`.
- **O que vem a seguir:** a fila de desenvolvimento, o que está bloqueado (e por quem), o que falta decidir e o que foi descartado com o motivo estão em [`docs/planejamento/00-ROADMAP.md`](docs/planejamento/00-ROADMAP.md), atualizado a cada versão.
- **Voltar uma versão:** cada versão fechada vira uma **tag git** (`v3.09.0`) e uma imagem `:3.09.0`, criadas pelo CI **só quando o pipeline inteiro passa** — tag que existe é versão que foi aprovada, não apenas que compilou. O passo a passo está em [`deploy/voltar-versao.md`](deploy/voltar-versao.md): qual versão escolher, as **seis** linhas de imagem que precisam mudar juntas (a da API aparece quatro vezes) e por que o banco **não** volta com o código.
- **Confira depois de todo deploy:** `GET /api/health` →

  ```json
  { "status": "ok", "versao": "v3.09.0 — …", "versao_numero": "3.09.0",
    "migracoes": { "em_dia": true, "no_codigo": "b4c5d6e7f8a9", "no_banco": "b4c5d6e7f8a9" } }
  ```

  A mesma informação aparece no painel em **Configurações → Sistema**, sem
  precisar abrir a URL. A versão vem de `backend/app/versao.py` e o
  `tests/test_versao.py` a mantém igual ao topo do `CHANGELOG.md` — ela já
  congelou duas vezes quando era uma constante escrita à mão (`v1.50` por vinte
  versões e `v2.27` por vinte e seis), mentindo com toda a confiança.

  `"em_dia": false` significa que o banco ficou para trás do código — o
  `alembic upgrade head` do entrypoint falhou. A API sobe assim mesmo, e o
  defeito aparece só quando alguém usa a tela afetada. Resolva com
  `docker exec <api> alembic upgrade head`. **Abra também um link de candidato
  numa aba que já estava aberta antes do deploy**: é exatamente o caso que
  causou o incidente de 2026-07-29.
- **Rollback de código:** aponte a stack para a tag anterior da imagem (`ghcr.io/...:vX.Y.Z`).
- **Rollback de banco:** toda migration tem `downgrade()` que **não destrói dados**. Voltar uma revisão: `docker exec <api> alembic downgrade -1`. Backup antes: `docker exec <db> pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql`.
- **Higienização de imagens** (evita acúmulo na VPS): `docker image prune -af --filter "until=168h"` — agende no cron do host (domingo de madrugada). **Nunca** `docker volume prune` na VPS.

## 🔐 Segurança e LGPD

- Link mágico com token de 256 bits (só o **hash** é persistido) e expiração; **rate limiting** em login (por IP e por conta), 2FA e recuperação de senha; anti-enumeração de CPF
- Assinatura eletrônica simples (art. 4º, I, Lei 14.063/2020), manifesto de evidências no PDF, verificação pública com dados minimizados (nome e CPF mascarados **fora** do painel)
- Arquivos excluídos, rejeitados ou substituídos deixam **hash SHA-256 na auditoria** antes de sair do storage; exportações em lote registram a lista de quem foi exportado
- Coleta fundamentada (LGPD art. 7º e art. 11 para dados de saúde), aviso de privacidade no primeiro acesso, expurgo automático pós-admissão — **inclusive dos documentos das crianças do reembolso-creche**, que ficavam guardados para sempre mesmo de quem foi indeferido (o comprovante mensal fica 5 anos, porque comprova despesa reembolsada em contrato público) — e higienização de dados de terceiros não assinados
- **Leitura de documentos por IA roteada por sensibilidade**: identidade e certificado são lidos normalmente; **atestado de saúde** (dado sensível) só passa pela IA com o provedor sob Zero Data Retention contratado — uma trava no código, ligável pelo painel, com a base legal registrada em [docs/planejamento/07-lgpd-leitura-automatizada-documentos.md](docs/planejamento/07-lgpd-leitura-automatizada-documentos.md). Geolocalização e foto do ponto eletrônico não são importadas para a avaliação (desproporcional ao fim)

## 🗺️ Roadmap e histórico

Decisões e roadmap em [docs/planejamento/](docs/planejamento/). Histórico de versões no [CHANGELOG.md](CHANGELOG.md).

## 🇬🇧 English summary

**HR platform for Brazilian outsourcing companies** — a self-hosted, mobile-first system that grew from a digital-onboarding portal into a full HR back office, replacing a Microsoft Forms + Power Automate patchwork:

- **Passwordless onboarding**: magic links; returning users verify via CPF + knowledge-based questions; guided in-browser document capture; OCR-assisted forms (consent-based); DISC and situational behavioral tests
- **Documents & signatures**: letterhead templates with variables; simple e-signatures (Law 14.063/2020) with an embedded evidence manifest and public QR verifier; **multi-party signing in role order** (employee, HR user, external party) consolidating into a final PDF; team signature via prior registered authorization (never a fake stamp)
- **Employee self-service portal**: one passwordless door for the worker's whole life at the company — courses, certificates, pending actions and appraisals; works for Tirvu-imported staff who never filled a form, via knowledge-based questions on native record data
- **Development & brigade recertification**: employees log courses and certifications; configurable types with expiry/criticality/eligible roles; RH validation queue with batch approval (critical docs never batched); automatic 90-day expiry alerts and one-click enrollment e-mail to the training provider with a per-person PDF dossier
- **Performance appraisals**: the paper "Appraiser Handbook" digitized — real-time observed facts (visible to the employee, author hidden), the 11-section 360° form (vertical named, horizontal anonymous & aggregated), a state machine that won't skip the in-person feedback conversation, the employee's right of reply, a competency radar + score timeline, and evaluator-drift calibration that informs the approver **without changing any score**; time-clock data imported as context, never as a grade
- **Workforce, benefits, archive**: unified candidate/employee records; idempotent workforce import; full childcare-reimbursement module (per-post eligibility **with an effective date per contract**, review lifecycle, signed request, plus the **monthly cycle**: one proof of expense per child — invoice when the provider is a company, signed receipt when it is an individual — with a configurable cutoff day, automatic reminders, and the post's amount acting as a **cap**, not a fixed value); unified test dashboard; filtered inventory with bulk ZIP+XLSX backup
- **Configurable branding**: company name, legal entity, logo and favicon editable from the panel
- **Cross-cutting**: full audit trail with before/after and file hashes; universal trash with restore; rate limiting; server-side idempotency; Microsoft 365 / Gmail / SMTP e-mail
- **Stack**: FastAPI + PostgreSQL + MinIO + Redis, React/Vite, Docker Compose / Portainer, CI-published GHCR images, Playwright E2E

## 📄 Licença

[MIT](LICENSE). Documentos-modelo e marcas contidos em `docs/` pertencem aos seus titulares e não integram a licença.
