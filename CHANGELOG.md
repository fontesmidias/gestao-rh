# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/) · versionamento semântico.

## [1.0.0-rc.1] — 2026-07-14

Primeira versão candidata do Portal de Admissão.

### Adicionado
- Portal do candidato (mobile-first, sem senha): link mágico, aceite LGPD, wizard de 6
  etapas com autosave por campo, ViaCEP, dependentes ilimitados, tour guiado e tooltips
  com dicas por documento.
- Assinatura eletrônica simples (Lei 14.063/2020): código único por e-mail assina as 3
  fichas de uma vez; vias assinadas enviadas em anexo; trilha de evidências (hash, IP,
  user-agent, instante).
- Fichas Cadastral, de Emergência e Termo de VT geradas em PDF fiéis aos templates
  oficiais (textos legais, declarações, identificador de resposta).
- Checklist de documentos com regras condicionais (reservista, PCD, casamento,
  dependentes por idade, cartão VT), upload com normalização foto/Word→PDF e feedback
  imediato; botão "Concluí meu envio".
- Painel do RH: convites, revisão com visualizador de PDF, aprovação/rejeição individual
  e em massa (e-mail agrupado), dossiê único em A4 padronizado na ordem oficial (com opção
  de dossiê parcial), configurações (perfil, senha, SMTP com teste, Microsoft 365 via
  OAuth/Graph), auditoria.
- Infra: PostgreSQL + migrations Alembic automáticas no start (atualização sem perda de
  dados), MinIO com expurgo LGPD diário, Redis/RQ, e-mails HTML modernos, telemetria de
  requisições e trilha de auditoria.
- Deploy: compose base+variantes (ip / traefik / certbot), stack única para Portainer com
  imagens do GHCR publicadas por CI (GitHub Actions).

[1.0.0-rc.1]: https://github.com/fontesmidias/admissao/releases/tag/v1.0.0-rc.1
