# Sistema de Admissão Green House — Visão e Decisões de Arquitetura

> Documento vivo do planejamento estratégico. Iniciado em 2026-07-13 (sessão de concepção — party mode BMAD).

## 1. Contexto e problema

O processo de R&S da Green House hoje usa Pandapé (ATS) + Microsoft Forms + Power Automate.
Fluxo atual: triagem via Forms → entrevista → avaliações situacional/comportamental (Forms) →
formulário admissional (Forms) → Power Automate gera Ficha Cadastro, Ficha de Emergência e
Termo de Opção de VT → candidato monta um PDF único com sua documentação e envia por WhatsApp.

**Dores:**
- Microsoft Forms não armazena arquivos de usuários externos à organização (@greenhousedf.com.br).
- O candidato é responsável por montar o PDF único na ordem correta — falha com frequência.
- Sem "continue de onde parou": envio parcial vira caos no WhatsApp.
- RH não tem tempo hábil para analisar documentação e dar feedback → admissão lenta.
- Formatos heterogêneos (foto, PDF, Word), muitos ilegíveis.
- Assinatura das fichas exige processo acessível a candidatos com baixa instrução.

## 2. Visão da solução

**Portal do Candidato** para a fase admissional:

1. RH cadastra o candidato aprovado → sistema envia **link mágico** (sem senha) por e-mail/WhatsApp.
2. Candidato preenche o **formulário admissional** no portal.
3. Sistema **gera automaticamente**: Ficha Cadastro, Ficha de Emergência e Termo de Opção de VT.
4. Candidato **assina eletronicamente** (assinatura eletrônica simples — Lei 14.063/2020 e
   MP 2.200-2/2001) com trilha de evidências: código OTP por e-mail/SMS, IP, timestamp, hash.
5. Candidato sobe a documentação em **slots individuais** (checklist) — foto, PDF ou Word;
   o sistema normaliza tudo para PDF. *O candidato nunca monta PDF.*
6. **"Continue de onde parou"** nativo: o checklist com status por documento é o progresso;
   o mesmo link mágico retoma a sessão.
7. Validação automática imediata (formato, tamanho, nitidez) + **fila de revisão do RH**
   (aprovar/rejeitar com motivos pré-definidos → notificação automática ao candidato).
8. Estado explícito **"Envio concluído pelo candidato"** (botão de confirmação que congela o
   checklist e notifica o RH) — elimina o "achei que tinha enviado tudo".
9. Sistema monta o **PDF único (dossiê)** na ordem oficial e envia por SMTP ao RH;
   Termo de VT assinado vai ao colaborador.

### Ordem oficial do dossiê (PDF único)

1. **Ficha Cadastro** (gerada e assinada no sistema)
2. **Ficha de Emergência** (gerada e assinada no sistema)
3. **Termo de Opção de VT** (gerado e assinado no sistema)
4. Documentação pessoal (foto 3x4, RG, CPF, CTPS Digital, PIS/PASEP, Título de Eleitor,
   Reservista, habilitação profissional, laudo PCD — conforme aplicável)
5. Comprovantes/certidões/escolaridade (endereço ≤90 dias, escolaridade, diplomas,
   Nada Consta Eleitoral, Nada Consta Criminal)
6. Estado civil e dependentes (certidões, cartão de vacina / declaração escolar)

## 3. Decisões de arquitetura (registro de decisões)

| # | Decisão | Racional |
|---|---|---|
| D1 | **Monolito modular** (um app, módulos internos: candidatos, documentos, assinatura, notificações) | Um mantenedor, um sistema, volume baixo. Microserviços trariam complexidade operacional sem retorno. Módulos bem separados permitem extração futura se necessário. |
| D2 | **Backend: Python + FastAPI** | O risco/valor do sistema está em processamento de documentos (imagem→PDF, mesclagem, OCR), onde o ecossistema Python é superior: `pypdf`, `Pillow`, `img2pdf`, `weasyprint`, `pytesseract`. FastAPI: validação Pydantic, Swagger automático, código legível. Decisão do Bruno em 2026-07-13, seguindo voto da mesa. |
| D3 | **Frontend: React + Vite** | Moderno, comunidade enorme. Tour guiado (driver.js) de 4 passos + tooltips por documento (com dicas de onde obter cada um, herdadas do PDF de instruções). |
| D4 | **Banco: PostgreSQL** | Requisito do Bruno; padrão sólido. |
| D5 | **Arquivos: MinIO** com política de ciclo de vida (expurgo automático após conclusão da admissão + N dias) | Requisito; expurgo atende armazenamento **e** LGPD (minimização/retenção). |
| D6 | **Fila em background: Redis + RQ/Celery** | Conversão, OCR, montagem do dossiê e e-mails fora do request HTTP. |
| D7 | **Word→PDF: LibreOffice headless** no container de workers | Solução madura e gratuita. |
| D8 | **Notificações: SMTP** (`.env`) | Requisito. |
| D9 | **Assinatura eletrônica simples** (OTP + IP + timestamp + hash, sem certificado digital) | Válida entre particulares (Lei 14.063/2020, MP 2.200-2). Acessível a baixa instrução — sem app, sem gov.br obrigatório. |
| D10 | **Deploy: Docker Compose em 3 stacks** — `ip` (local/Portainer e VPS sem domínio, porta do front via `FRONTEND_PORT` no `.env`), `traefik` (VPS com domínio, TLS automático) e `certbot` (aproveita certbot existente na VPS, nginx na frente) | Requisito. Só o front expõe porta; API e MinIO ficam na rede interna do Docker. |
| D11 | **Config 100% via `.env`** (`.env.example` versionado; `.env` nunca commitado) | Segurança: o repositório não conhece portas/segredos reais da infra. |
| D12 | **Versionamento: GitHub**, Conventional Commits, CHANGELOG, tags semânticas, CI (lint + testes + build de imagem) | Requisito de histórico de melhorias. |

### Limitação registrada do modo IP (sem domínio)
Sem HTTPS (não há certificado para IP puro). Serve para validação interna do Bruno;
**não usar com candidatos reais** — link mágico trafegaria sem criptografia.
Ao comprar domínio: subir stack Traefik ou Certbot com o mesmo `.env` + `DOMAIN`.

## 4. Roadmap

- **v1.0** — Portal admissional: link mágico, formulário, geração das 3 fichas, assinatura
  eletrônica simples, upload por slots com normalização p/ PDF, checklist "continue de onde
  parou", estado "envio concluído", fila de revisão do RH, dossiê único na ordem oficial,
  notificações SMTP, expurgo MinIO, tour guiado + tooltips.
- **v1.1** ✅ — Validações inteligentes (OCR: data do comprovante de endereço, nitidez),
  dashboard do RH com métricas, CPF com dígito verificador, esqueci-senha, equipe do RH,
  Google/Gmail OAuth, manifesto de assinatura no PDF.
- **v1.3** — OCR estendido aos demais documentos (pedido do Bruno, 2026-07-14): conferir se o
  CPF/RG enviados batem com os números digitados na ficha, identificar documento errado no
  slot (ex.: RG no lugar da CTPS), validar legibilidade dos dados essenciais. Testes de
  interface (Playwright) no CI. Tooltips com imagens de exemplo.
- **v1.3 (novos pedidos, 2026-07-15)** — (a) Portal único `/entrar` com CPF + perguntas de
  verificação (KBA) + fallback por e-mail, anti-enumeração, bloqueio progressivo;
  (b) **Dash de colaboradores**: visão com filtros (status, posto, período) mostrando os
  principais dados preenchidos, e **exportação Excel** linha a linha com TODAS as respostas
  do formulário por colaborador; (c) **Documentos por posto de serviço** (INFRAERO
  primeiro): fundação de documentos assináveis dinâmicos (migration enum → tabela),
  templates com layout oficial preservado (modelos em
  `docs/exemplos de templates de documentos especificos/` — 2 recebidos, 2 a receber),
  geração ao marcar o posto no painel, envio por e-mail com instruções e assinatura na
  plataforma com o mesmo fluxo de OTP + manifesto + QR.
- **v2.0** — Migração dos formulários de seleção (situacional, comportamental) e do fluxo
  pós-Pandapé para dentro do sistema. Formulários de avaliação **fora da v1** (decisão do Bruno).

## 5. Pendências / próximos passos

- [ ] Criar repositório remoto no GitHub (privado) e fazer o primeiro push.
- [ ] Desenho do modelo de dados (candidato, documento/slot, envio, assinatura, eventos).
- [ ] Desenho do fluxo de telas do candidato e da fila de revisão do RH.
- [ ] Definir catálogo de slots de documentos (obrigatórios × condicionais, com regras: sexo,
  estado civil, dependentes, VT sim/não, PCD).
- [ ] Especificar template HTML das 3 fichas (base para geração via weasyprint).
- [ ] Comprar domínio (posterior à validação por IP).
