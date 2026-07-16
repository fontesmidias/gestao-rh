# 🌱 Portal de Admissão — Green House

**Admissão de colaboradores 100% digital, sem senha, com assinatura eletrônica auditável — do convite ao dossiê pronto em horas, não semanas.**

*Digital employee onboarding for Brazilian companies: passwordless magic links, guided document capture with on-device quality hints, OCR-assisted form filling, legally-grounded electronic signatures (Brazilian Law 14.063/2020) with a public QR verifier, and a full audit trail. [English summary below](#-english-summary).*

[![CI](https://github.com/fontesmidias/admissao/actions/workflows/build.yml/badge.svg)](https://github.com/fontesmidias/admissao/actions/workflows/build.yml)
[![Testes de interface](https://github.com/fontesmidias/admissao/actions/workflows/e2e.yml/badge.svg)](https://github.com/fontesmidias/admissao/actions/workflows/e2e.yml)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green.svg)](LICENSE)

---

## 😫 A dor que deu origem a isto

O processo anterior era um Microsoft Forms de **50 perguntas** costurado a fluxos de Power Automate: o candidato preenchia tudo de uma vez (sem salvar progresso), mandava documentos por WhatsApp e e-mail, o RH imprimia fichas, colhia assinaturas à caneta, conferia papel por papel e montava o dossiê à mão. Resultado: **semanas** de ida e volta, documentos perdidos, retrabalho — e um público de candidatos que, em grande parte, só tem o celular como computador.

Este portal nasceu dessas dores, uma a uma:

| Dor real | Solução no portal |
|---|---|
| Formulário gigante que não salva o progresso | Wizard de 6 etapas com **autosave por campo** — fecha o navegador e continua depois, pelo mesmo link |
| Candidato sem e-mail ou que perde a senha | **Link mágico** (sem senha) + portal de retorno por **CPF e perguntas de verificação** (estilo TSE) |
| Fotos ilegíveis, documento errado, comprovante vencido | **Câmera guiada** com moldura por documento e dicas em tempo real (luz, foco, enquadramento) + validações no servidor (nitidez, comprovante > 90 dias, CPF divergente) |
| Digitação manual de dados que já estão no documento | **OCR** do RG/CNH, CPF, título e comprovante **sugere** o preenchimento — o candidato confere e confirma (a responsabilidade é dele) |
| Assinatura à caneta em fichas impressas | **Assinatura eletrônica simples** (Lei 14.063/2020, art. 4º, I): código de uso único por e-mail, manifesto de evidências gravado no PDF (hash SHA-256, IP, dispositivo, data) e **verificador público via QR code** |
| "Cadê o documento que te mandei no WhatsApp?" | RH **insere o arquivo manualmente** no checklist, com etiqueta de origem e trilha de auditoria |
| Dado errado descoberto depois da assinatura | Correção pelo RH com **re-assinatura granular**: só as fichas afetadas voltam para o candidato; a via antiga fica no histórico e o verificador público responde "substituída", nunca "não encontrada" |
| Dossiê montado à mão | **Dossiê único em PDF A4**, na ordem oficial, gerado em um clique |

## ✨ Funcionalidades

**Para o candidato (mobile-first, linguagem simples):**
- Link mágico sem senha · aceite LGPD explícito · tour guiado
- Formulário em 6 etapas com autosave, máscara de datas `dd/mm/aaaa`, busca de CEP, validação de CPF com dígito verificador, nome social (Decreto 8.727/2016) e filiação com pai omitível
- Câmera guiada: moldura no formato do documento (cartão, A4, cabeçalho de conta, retrato 3×4), semáforo de luz/foco/enquadramento, captura **frente e verso** em sequência, conferência da foto antes do envio — e sempre a alternativa de mandar um arquivo do aparelho
- OCR local (Tesseract) pré-preenchendo campos **só com consentimento** e nunca sobrescrevendo o que foi digitado
- Checklist condicional (reservista por sexo/idade, PCD, casamento, documentos por dependente) com dicas de onde conseguir cada documento
- Ver e excluir os próprios envios ainda não aprovados · assinatura das fichas com um único código · acompanhamento do status

**Para o RH (desktop, sidebar retrátil):**
- Convite com um clique (e-mail opcional — copie o link e mande pelo WhatsApp)
- Fila de revisão com visualizador de PDF, aprovação/rejeição individual e em massa, reabertura de status com motivo
- Inserção manual de documentos recebidos fora do sistema (etiquetados) e correção de dados da ficha com re-assinatura granular
- Postos de serviço com documentos específicos (ex.: INFRAERO) gerados e assinados na plataforma, com timbre e assinantes configuráveis
- Dashboard de métricas · relatório de colaboradores com filtros e **exportação Excel** · gestão da equipe do RH · auditoria completa
- E-mail por **Microsoft 365 (OAuth/Graph)**, **Google (OAuth/Gmail API)** ou SMTP — configurados pelo painel, com teste e diagnóstico

**Transversal:**
- Trilha de auditoria de tudo: quem fez, quando, antes → depois, e **hash SHA-256 de todo arquivo antes de qualquer exclusão**
- Expurgo LGPD automático dos arquivos após a admissão · dados de saúde com acesso restrito
- Tema claro/escuro seguindo o dispositivo · telemetria de requisições · frases de espera com personalidade

## 🏗️ Arquitetura

```
React/Vite (SPA)  ──►  nginx  ──►  FastAPI (Python 3.12)
                                     ├── PostgreSQL 16 (Alembic: migrations automáticas no start)
                                     ├── MinIO (arquivos, S3-compatível)
                                     ├── Redis + RQ (expurgo LGPD agendado)
                                     └── SMTP / Graph API / Gmail API
```

- **Backend:** FastAPI · SQLAlchemy 2 · Alembic · fpdf2/pypdf (PDFs) · pytesseract (OCR) · qrcode · openpyxl
- **Frontend:** React 18 · Vite · CSS próprio (design "fintech" com tema claro/escuro) — sem dependência de CDN
- **Infra:** Docker Compose (variantes IP direto / Traefik / certbot) · imagens publicadas no GHCR por CI · Playwright rodando contra a stack completa em cada push

## 🚀 Como rodar

### Portainer (recomendado na VPS) — arquivo único, sem build
1. Portainer → *Stacks* → *Add stack* → cole [deploy/portainer-stack.yml](deploy/portainer-stack.yml).
2. Defina as variáveis de ambiente na tela do Portainer (o modo avançado aceita colar o `.env`).

As imagens (`ghcr.io/fontesmidias/admissao-api|frontend`) são **públicas** e publicadas pelo CI a cada push na `main` e a cada tag `v*`.

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

> Use sempre `--env-file .env` (os arquivos compose ficam em `deploy/`). Acesse `http://IP:FRONTEND_PORT` — painel do RH em `/rh` (admin inicial criado a partir de `RH_ADMIN_EMAIL`/`RH_ADMIN_PASSWORD`).

### Atualização e rollback (sem perda de dados)

- **Atualizar:** `git pull` + o mesmo `up -d --build` (ou *Re-pull image* no Portainer). As migrations rodam sozinhas no start e preservam os volumes `postgres-data` e `minio-data`.
- **Rollback de código:** aponte a stack para a tag anterior da imagem (`ghcr.io/...:vX.Y.Z`) e suba de novo.
- **Rollback de banco:** toda migration tem `downgrade()` escrito para **não destruir dados** (colunas viram opcionais antes de sair; nada é dropado com conteúdo). Para voltar uma revisão: `docker exec <api> alembic downgrade -1`. Faça backup antes de qualquer downgrade: `docker exec <db> pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql`.

## 🔐 Segurança e LGPD

- Link mágico com token de 256 bits (apenas o **hash** é persistido) e expiração; lockout por tentativas no portal de retorno; anti-enumeração de CPF
- Assinatura eletrônica simples nos termos do art. 4º, I, da Lei nº 14.063/2020, com manifesto de evidências no próprio PDF e verificação pública com dados minimizados (nome e CPF mascarados)
- Arquivos excluídos, rejeitados ou substituídos deixam **hash SHA-256 na auditoria** antes de sair do storage
- Coleta fundamentada (LGPD art. 7º, II, V, VI; art. 11, II, "a" e "e" para dados de saúde), aviso de privacidade no primeiro acesso e expurgo automático pós-admissão

## 🗺️ Roadmap

Ver [docs/planejamento/01-visao-e-decisoes.md](docs/planejamento/01-visao-e-decisoes.md). Próximos passos: OCR assistido por IA (Mistral OCR com chave configurável e fallback local), timbrado da empresa em todos os PDFs (com gestão pelo painel), lembretes automáticos de pendência e formulários de seleção (v2.0).

## 🇬🇧 English summary

**Green House Onboarding Portal** — a self-hosted, mobile-first employee onboarding system built for the Brazilian labor-documentation reality, replacing a Microsoft Forms + Power Automate patchwork:

- **Passwordless**: candidates get a magic link; returning users verify via CPF + knowledge-based questions
- **Guided capture**: in-browser camera with document-shaped framing masks and real-time light/focus/framing hints; front-and-back capture merged into a single PDF; file upload always available as an alternative
- **OCR-assisted forms**: Tesseract reads ID cards, driver's licenses, voter IDs and utility bills to *suggest* form values — applied only with explicit consent, never overwriting user input
- **Legally-grounded e-signatures** (Brazilian Law 14.063/2020): one-time e-mail codes, an evidence manifest embedded in each PDF (SHA-256, IP, device, timestamps) and a public QR verifier; superseded signatures are historized, never deleted
- **HR back office**: review queue, bulk actions, manual document insertion with provenance labels, field-level record corrections triggering granular re-signature of only the affected documents, Excel exports, full audit trail with before/after values and file hashes
- **Stack**: FastAPI + PostgreSQL + MinIO + Redis, React/Vite, Docker Compose / Portainer, CI-published GHCR images, Playwright E2E against the full stack

## 📄 Licença

[MIT](LICENSE) © Green House. Documentos-modelo e marcas contidos em `docs/` pertencem aos seus titulares e não integram a licença.
