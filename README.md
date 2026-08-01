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

### Documentos e assinaturas
- **Modelos de documento** no papel timbrado, com variáveis (`{{nome}}`, `{{cargo}}`…), prévia, envio pontual e predefinições (Ofício, Comunicado, Contrato, Declaração)
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
- **Banco de Talentos**: formulário público (substituiu o Microsoft Forms) com currículo opcional, importação idempotente da planilha do Forms e consentimento LGPD obrigatório
- **Match de Vagas**: o RH cadastra a vaga e o sistema ranqueia os talentos por aderência — filtro estruturado local primeiro (grátis), currículo lido por IA depois. **A IA nunca decide sozinha**: devolve nota e justificativa, o RH convoca. O ranqueamento é **assíncrono** (enfileirado), o texto do currículo é extraído **uma vez** no upload e a análise é reaproveitada por (vaga, talento)
- **Currículo é tratado como entrada hostil**: é upload público de gente desconhecida cujo texto vai para dentro de um prompt. Cinco camadas anti-prompt-injection e o suspeito aparece marcado **"⚠️ suspeito"** no ranking — **nunca filtrado em silêncio**, porque ranking adulterado parece igual a um legítimo. CPF/RG/telefone/e-mail são removidos antes do envio à IA
- **Ninguém some sem explicação**: sem currículo, ilegível, aguardando IA e erro são resultados **gravados e exibidos com o motivo** — não ausência
- **Provas por cargo**: banco de provas configurável pelo RH (objetivas com correção automática e discursivas pontuadas), aplicação por link avulso com timer, aleatorização por participante e **banco de itens** reutilizável. O gabarito nunca vai ao público
- **Teste já respondido é aproveitado**: quem fez DISC, situacional ou prova antes de virar candidato não refaz — e fica registrado se a identidade foi deduzida pelo sistema ou afirmada por uma pessoa, porque o link avulso é anônimo e homônimo existe
- **Mini-CRM**: anotações e tags que acompanham a **pessoa** de talento → candidato → efetivo → desligado, com autor snapshot e anexo
- **Minutário de Mensagens**: modelos de mensagem e composição assistida por IA a partir dos campos da **vaga** — o texto volta sempre editável e nunca é enviado sozinho

### Benefícios, testes, arquivo
- **Reembolso-Creche** (IN SEGES/MGI 147/2026): elegibilidade por posto, link público de levantamento com 2FA (ou perguntas de verificação para quem não tem e-mail), assinatura do requerimento e ciclo completo de decisão do RH — aprovar, devolver para correção, indeferir, "não faço jus", suspender/encerrar — com aviso ao colaborador em cada passo
- **Central de testes**: dashboard de todos os testes (admissão + testagem avulsa), reset, relatório de comportamento; links de testagem anônima onde a pessoa vê o próprio resultado
- **Arquivo/backup**: inventário com filtros, download individual e **backup em lote** (ZIP por posto/pessoa + planilha XLSX), auditado
- **DashPlanilha**: componente único de lista do RH (ordenação, filtro por coluna, seleção em massa, colunas configuráveis, export CSV e cards-métrica clicáveis) — o padrão de todas as telas de lista

### O que o RH edita sem depender de deploy
- **Textos de todos os e-mails**, com preview, histórico append-only de quem mudou o quê e restauração. O **template é apresentação, nunca decisão**: os e-mails que enumeram documentos recebem a lista pronta como `{{lista}}` — a regra do que entra continua no código. Variável obrigatória é validada no salvamento (um e-mail de acesso sem `{{codigo}}` sai bonito e vazio, e ninguém mais entra no sistema)
- **Quem recebe cada aviso interno** (matriz evento × destinatários) — nunca a caixa de login, que é pessoal
- **Catálogo dos documentos do sistema**: os 11 documentos da admissão com amostra em PDF de verdade, download e "criar modelo a partir deste" nos de texto corrido. Os geradores oficiais **não são substituídos** — o hash do ato de assinatura é calculado sobre o PDF gerado, então trocá-los faria os manifestos já emitidos apontarem para um hash que não se reproduz
- **Uniformes**: lista com as medidas informadas no wizard, na tela e com export CSV. O e-mail ao operacional diz só que há novidade — ficha de pessoal não circula por caixa de e-mail
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

### Transversal
- **Trilha de auditoria** de tudo (quem, quando, antes → depois) e **hash SHA-256 de todo arquivo antes de qualquer exclusão**
- **Lixeira universal** com restauração e retenção configurável · expurgo LGPD automático · rate limiting em login/2FA
- E-mail por **Microsoft 365 (Graph)**, **Google (Gmail API)**, webhook do Power Automate ou SMTP — configurados pelo painel
- **Trava anti-duplo-clique** (idempotência no servidor) · tema claro/escuro · **identidade visual da empresa configurável**

## 🏗️ Arquitetura

```
React/Vite (SPA)  ──►  nginx  ──►  FastAPI (Python 3.12)
                                     ├── PostgreSQL 16 (Alembic: migrations automáticas no start)
                                     ├── MinIO (arquivos, S3-compatível)
                                     ├── Redis + RQ (workers: expurgo LGPD, expiração de roteiros)
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
cp .env.example .env   # edite: senhas, SMTP, RH_ADMIN_*, FRONTEND_PORT

# Local / VPS sem domínio (sem HTTPS — apenas validação):
docker compose --env-file .env -f deploy/docker-compose.base.yml -f deploy/docker-compose.ip.yml up -d --build

# VPS com domínio (Traefik, TLS automático):
docker compose --env-file .env -f deploy/docker-compose.base.yml -f deploy/docker-compose.traefik.yml up -d --build

# VPS com certbot/nginx existentes no host:
docker compose --env-file .env -f deploy/docker-compose.base.yml -f deploy/docker-compose.certbot.yml up -d --build
```

> Use sempre `--env-file .env` (os arquivos compose ficam em `deploy/`, e a interpolação lê o `.env` do diretório do primeiro `-f`). Acesse `http://IP:FRONTEND_PORT` — painel do RH em `/rh` (admin inicial criado a partir de `RH_ADMIN_EMAIL`/`RH_ADMIN_PASSWORD`).

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
- **Confira depois de todo deploy:** `GET /api/health` →

  ```json
  { "status": "ok", "versao": "v2.22-…",
    "migracoes": { "em_dia": true, "no_codigo": "b8c9d0e1f2a3", "no_banco": "b8c9d0e1f2a3" } }
  ```

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
- Coleta fundamentada (LGPD art. 7º e art. 11 para dados de saúde), aviso de privacidade no primeiro acesso, expurgo automático pós-admissão e higienização de dados de terceiros não assinados
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
- **Workforce, benefits, archive**: unified candidate/employee records; idempotent workforce import; full childcare-reimbursement module (per-post eligibility, review lifecycle, signed request); unified test dashboard; filtered inventory with bulk ZIP+XLSX backup
- **Configurable branding**: company name, legal entity, logo and favicon editable from the panel
- **Cross-cutting**: full audit trail with before/after and file hashes; universal trash with restore; rate limiting; server-side idempotency; Microsoft 365 / Gmail / SMTP e-mail
- **Stack**: FastAPI + PostgreSQL + MinIO + Redis, React/Vite, Docker Compose / Portainer, CI-published GHCR images, Playwright E2E

## 📄 Licença

[MIT](LICENSE). Documentos-modelo e marcas contidos em `docs/` pertencem aos seus titulares e não integram a licença.
