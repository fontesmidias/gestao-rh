# Renomear o repositório (de "admissao" para "gestao-rh") — CONCLUÍDO

**Feito em 2026-07-19:** repo renomeado para `fontesmidias/gestao-rh`. Código
ajustado: `portainer-stack.yml` (imagens `gestao-rh-api|frontend`), `git remote`,
badges e imagem no README. O CI já deriva o nome da imagem de `github.repository`,
então publica automaticamente em `ghcr.io/fontesmidias/gestao-rh-*`.

**No Portainer (VPS), quando for atualizar:** a stack aponta para as imagens
novas — faça *Re-pull image* após o primeiro CI verde no nome novo. As imagens
antigas (`admissao-*`) seguem no GHCR para rollback durante a transição.

---

## Histórico do plano original (de "admissao" para o novo nome)

O sistema virou uma plataforma de RH, não só admissão. Renomear o repo é seguro
se feito na ordem abaixo. **Me passe o novo nome** que eu ajusto todas as
referências no código de uma vez.

## O que o Bruno faz (no GitHub)

1. GitHub → repositório → **Settings → General → Repository name** → novo nome
   (ex.: `rh-terceirizacao`, `portal-rh`, `gestao-rh`).
2. O GitHub **redireciona automaticamente** o nome antigo (URLs, `git remote`,
   clones existentes seguem funcionando). Nada quebra de imediato.

## O que muda no código (eu ajusto ao receber o nome)

O nome do repo aparece em:

- **Imagens GHCR** (`deploy/portainer-stack.yml`): hoje
  `ghcr.io/fontesmidias/admissao-api` e `...-frontend`. O CI (`.github/workflows/ci.yml`)
  publica a imagem com o nome derivado do repositório. Ao renomear o repo, o CI
  passará a publicar em `ghcr.io/fontesmidias/<novo>-api|frontend`. Preciso
  atualizar o `portainer-stack.yml` para o novo caminho **e** garantir no CI que
  o nome da imagem casa (ver a variável de nome no `ci.yml`).
- **Badges e links do README** (`ci.yml` badge já é relativo ao repo, redireciona).
- Menções textuais a "admissão" no README/CLAUDE.md (troco por "RH"/o novo nome).

## Ordem segura para não ficar sem imagem

1. Renomear o repo no GitHub.
2. Eu atualizo `portainer-stack.yml` + `ci.yml` para o novo nome e faço push.
3. O CI publica as imagens com o novo nome.
4. No Portainer, atualizar a stack para as imagens novas (`ghcr.io/.../<novo>-*`)
   e subir. As imagens antigas (`admissao-*`) continuam existindo no GHCR até
   serem limpas — então dá para rollback durante a transição.

## Já feito (independe do rename)

- `frontend/index.html`: título agora "Portal de RH" (era "Admissão — Green House").
- README reescrito como plataforma de RH; identidade da empresa configurável.
- Marca (nome/razão/CNPJ/logo/favicon) editável pelo painel — o vínculo com
  "Green House" deixou de ser chumbado.
