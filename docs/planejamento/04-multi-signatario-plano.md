<!-- Planejamento do multi-signatario (leva seguinte a v1.40). Gerado e
verificado adversarialmente em 2026-07-19. Implementar SEMPRE incorporando
as 14 correcoes obrigatorias da critica ao final deste arquivo. -->

# Plano de implementação — MULTI-SIGNATÁRIO

## 0. Decisão de arquitetura (resumo executivo)

**Não evoluir a `Assinatura` atual em um modelo genérico.** Ela tem uma semântica bem definida e testada: *uma via assinada pelo titular do link mágico (candidato)*, com OTP, hash, PDF, invalidação. Reescrevê-la para "N signatários" quebraria os fluxos `_registro`, `_docs_exigidos`, `_assinaturas_modelo`, `verificar_assinatura` e todos os `GERADORES` — risco alto num repositório de produção.

**Introduzir duas tabelas novas por cima:**

- **`solicitacao_assinatura`** — agrupa UM documento + o roteiro de papéis/ordem + estado global do fluxo.
- **`etapa_assinatura`** — uma linha por signatário (papel, ordem, quem, prova, evidências, pdf da via, hash).

A `Assinatura` existente **continua sendo a fonte de verdade da assinatura do CANDIDATO** (não se reescreve o fluxo dele — requisito 3). Quando o candidato participa de um fluxo multi-signatário, a `etapa_assinatura` dele **aponta para a `Assinatura`** já existente (FK `assinatura_id`), reusando OTP/hash/evidências que já funcionam. Signatários novos (usuário RH logado ou externo) vivem **só** na `etapa_assinatura`, sem tocar em `Assinatura`.

Isso dá **convivência sem migração destrutiva**: todo `Assinatura` de hoje (candidato/modelo, 1 assinante) permanece 100% válido e verificável exatamente como está. O multi-signatário é uma **camada opcional acima** — só existe quando o RH monta um roteiro com mais de um papel.

---

## 1. Modelo de dados (tabelas/colunas novas)

### 1.1. `solicitacao_assinatura` (agrupador do documento + roteiro)

Arquivo novo: `backend/app/models/solicitacao_assinatura.py`

| coluna | tipo | nota |
|---|---|---|
| `id` | `UUID` PK default uuid4 | |
| `candidato_id` | `UUID` FK `candidato.id` index | documento é sempre "de um colaborador" (mantém a base colaborador-cêntrica) |
| `documento` | `Enum(DocumentoAssinavel, name="documento_assinavel")` nullable, `create_type=False` | documento fixo… |
| `modelo_id` | `UUID` FK `modelo_documento.id` nullable | …ou de modelo — exatamente um |
| `titulo_doc` | `String(200)` | snapshot |
| `corpo_doc` | `Text` | snapshot do modelo no envio |
| `status` | `Enum(StatusSolicitacao, name="status_solicitacao", create_type=True/checkfirst)` | `rascunho, aguardando, concluida, cancelada, expirada` |
| `etapa_atual_ordem` | `Integer` default 0 | ponteiro para a ordem que está liberada agora |
| `pdf_final_key` | `String(300)` nullable | via consolidada no MinIO quando `concluida` |
| `hash_final_sha256` | `String(64)` nullable | hash do PDF final consolidado |
| `expira_em` | `DateTime(tz)` nullable | prazo global do roteiro |
| `cancelada_motivo` | `String(300)` nullable | |
| `criada_por` | `String(120)` nullable | e-mail do usuário RH que montou o roteiro (auditoria) |
| `criado_em` / `atualizado_em` | `DateTime(tz)` | |

`StatusSolicitacao` (enum novo) em `backend/app/models/solicitacao_assinatura.py`.

### 1.2. `etapa_assinatura` (uma linha por signatário)

Mesmo arquivo.

| coluna | tipo | nota |
|---|---|---|
| `id` | `UUID` PK | é o **id público** que vai no QR `/verificar/{id}` de cada via |
| `solicitacao_id` | `UUID` FK `solicitacao_assinatura.id` index, `ondelete` NÃO cascade (lixeira antes) | |
| `papel` | `String(60)` | copiado do `PapelAssinatura.nome` (snapshot — não FK, papel pode ser renomeado/apagado) |
| `ordem` | `Integer` | ordem de assinatura; empatados assinam em paralelo |
| `tipo_signatario` | `Enum(TipoSignatario, name="tipo_signatario")` | `candidato, usuario_rh, externo` |
| `assinatura_id` | `UUID` FK `assinatura.id` nullable | **só quando `tipo=candidato`** — reusa a `Assinatura` existente |
| `usuario_rh_id` | `UUID` FK `usuario_rh.id` nullable | só quando `tipo=usuario_rh` |
| `externo_nome` | `String(120)` nullable | só quando `tipo=externo` |
| `externo_email` | `String(180)` nullable | só quando `tipo=externo` |
| `externo_cpf` | `String(11)` nullable | opcional; entra no manifesto se informado |
| `token_hash` | `String(64)` nullable | link mágico próprio do externo (SHA-256 do token, como `AcessoMagico`) |
| `otp_hash` / `otp_expira_em` / `otp_tentativas` | iguais aos da `Assinatura` | só para `externo` |
| `assinado_em` | `DateTime(tz)` nullable | preenchido ao concluir a etapa |
| `hash_sha256` | `String(64)` nullable | hash da via desta etapa (documento sem blocos) |
| `pdf_key` | `String(300)` nullable | via parcial desta etapa no MinIO |
| `ip` / `user_agent` | iguais à `Assinatura` | evidências |
| `prova_metodo` | `String(60)` | `"otp_email"` \| `"senha_sessao_rh"` — vai no manifesto |
| `recusada_em` / `recusada_motivo` | `DateTime(tz)` / `String(300)` nullable | signatário recusou |
| `criado_em` | `DateTime(tz)` | |

`TipoSignatario` enum novo.

**Por que snapshot de `papel` como String e não FK:** o `PapelAssinatura` já pode ir para a lixeira; a `Assinatura` atual já guarda `papel` como `String(60)` — mesma convenção, coerência.

**Por que a etapa do candidato aponta para `Assinatura` em vez de duplicar:** o candidato já assina hoje gerando `Assinatura` com OTP/hash/pdf. Reusar evita dois caminhos de código para o mesmo ato e garante que o requisito 3 ("não reescrever o fluxo dele") seja literal — o endpoint do candidato nem sabe que existe roteiro; um hook pós-assinatura promove a etapa (ver §3).

---

## 2. Migração Alembic

Um único arquivo de revisão (`alembic revision -m "multi_signatario"`), operações:

1. `sa.Enum("rascunho","aguardando","concluida","cancelada","expirada", name="status_solicitacao").create(bind, checkfirst=True)`
2. `sa.Enum("candidato","usuario_rh","externo", name="tipo_signatario").create(bind, checkfirst=True)`
3. `op.create_table("solicitacao_assinatura", ...)` — usando `postgresql.ENUM(..., create_type=False)` para os dois acima **e** para `documento_assinavel` (já existe → `create_type=False`, armadilha conhecida).
4. `op.create_table("etapa_assinatura", ...)` com os FKs.
5. Índices: `ix_etapa_solicitacao` (`solicitacao_id`), `ix_etapa_token_hash` (`token_hash`), `ix_sol_candidato` (`candidato_id`).

**Compatibilidade retroativa (garantida por construção):**
- Nenhuma coluna da `assinatura` é alterada ou removida.
- Documentos já assinados por 1 pessoa: continuam sendo `Assinatura` puras, sem `solicitacao_assinatura` associada. `verificar_assinatura(assinatura_id)` continua respondendo por elas exatamente como hoje.
- `downgrade`: `drop_table` das duas + `Enum(...).drop(checkfirst=True)`. Zero perda nos dados antigos.

**Regra de leitura no código:** um documento é "multi-signatário" **se e somente se** existir uma `solicitacao_assinatura` para aquele (candidato, documento/modelo). Caso contrário, é o fluxo legado de 1 assinatura. Um helper `tem_roteiro(db, candidato, documento|modelo) -> Solicitacao|None` centraliza essa decisão.

---

## 3. Ordem / sequenciamento / estados

### Liberação em cadeia
- `solicitacao.etapa_atual_ordem` começa em `min(ordem)` das etapas.
- Uma etapa só pode assinar se `etapa.ordem == solicitacao.etapa_atual_ordem` **e** `solicitacao.status == aguardando`. Fora disso → 409 `fora_da_vez`.
- Função central **`avancar_solicitacao(db, solicitacao)`** (novo `backend/app/services/roteiro_assinatura.py`):
  1. Se todas as etapas com `ordem == etapa_atual_ordem` têm `assinado_em` → sobe `etapa_atual_ordem` para a próxima `ordem` distinta.
  2. Ao liberar uma nova ordem, dispara notificação de cada signatário dessa ordem (e-mail com link para externo; aparece na fila do painel para usuário RH; para candidato, dispara o e-mail de código atual se ele for a próxima ordem).
  3. Se não há mais ordens pendentes → `status = concluida`, gera **PDF final consolidado** (§5) e salva `pdf_final_key`/`hash_final_sha256`.

### Candidato dentro do roteiro (reuso, requisito 3)
- Ao fim de `assinar` / `assinar_todos` em `app/api/assinaturas.py`, adicionar **um hook**: para cada `Assinatura` recém-assinada, `promover_etapa_do_candidato(db, assinatura)` procura uma `etapa_assinatura` com `assinatura_id == a.id`; se achar, copia `assinado_em/hash/ip/user_agent/pdf_key` para a etapa e chama `avancar_solicitacao`. Se não achar (documento sem roteiro), não faz nada — legado intacto.
- **Precedência:** se o candidato é a ordem 1 (o normal), ele assina primeiro pelo link mágico e libera os demais. Se estiver numa ordem posterior, o e-mail de código dele só é disparado quando `avancar_solicitacao` chegar na ordem dele (o botão de assinar no wizard fica "aguardando etapas anteriores").

### Recusa
- Externo ou usuário RH pode recusar: `etapa.recusada_em/recusada_motivo` preenchidos, `solicitacao.status = cancelada` (uma recusa trava o fluxo — assinatura é all-or-nothing). Notifica o RH. RH decide reenviar (novo roteiro) ou ajustar.

### Cancelamento pelo RH
- `POST /rh/solicitacoes-assinatura/{id}/cancelar` → `status=cancelada`, invalida tokens externos pendentes (revoga), registra auditoria. Etapas já assinadas ficam para histórico (não some via nenhuma).

### Expiração
- `expira_em` global. Um worker RQ (novo em `app/workers/`, ou cron simples reusando o padrão existente) marca `status=expirada` para solicitações `aguardando` vencidas e revoga tokens. `/verificar` de vias parciais já assinadas continua respondendo "válida" para aquela etapa (a via daquele signatário existiu), mas o **documento como um todo** não fica concluído.

---

## 4. Endpoints novos (backend)

Novo router `backend/app/api/solicitacoes_assinatura.py` (montar no `app/main.py`). Rotas específicas antes das paramétricas (armadilha conhecida).

### RH monta o roteiro
- **`POST /rh/candidatos/{cid}/solicitacoes-assinatura`** (requer_rh)
  Body: `{ documento?: DocumentoAssinavel, modelo_id?: uuid, expira_em?, etapas: [{papel, ordem, tipo, usuario_rh_id?, externo_nome?, externo_email?, externo_cpf?}] }`.
  Efeito: cria `solicitacao_assinatura` (com snapshot titulo/corpo se modelo) + N `etapa_assinatura`. Para `tipo=candidato`, cria/reusa a `Assinatura` do candidato (mesma lógica de `enviar_para_pessoa`) e liga `assinatura_id`. Status `rascunho`.
- **`POST /rh/solicitacoes-assinatura/{id}/disparar`** — valida roteiro (≥1 etapa, ordens coerentes, exatamente um doc), `status=aguardando`, chama `avancar_solicitacao` (notifica ordem 1). Retorna estado.
- **`GET /rh/candidatos/{cid}/solicitacoes-assinatura`** — lista roteiros do colaborador + estado por etapa (com nome/papel/ordem/assinado_em) para o painel.
- **`GET /rh/solicitacoes-assinatura/{id}`** — detalhe (timeline das etapas).
- **`POST /rh/solicitacoes-assinatura/{id}/cancelar`** — §3.
- **`POST /rh/solicitacoes-assinatura/{id}/reenviar-etapa/{etapa_id}`** — reenvia e-mail/gera novo token do externo da etapa corrente (rate-limited via `app/services/limite.py`).

### Roteiro-padrão no modelo (requisito 5)
Estender `ModeloDocumento` com um roteiro-padrão de **papéis** (sem pessoas — pessoas só no envio). Duas opções; escolho **tabela filha** para não inchar o modelo:
- **`modelo_etapa_padrao`** (`id, modelo_id FK, papel String(60), ordem Int, tipo_sugerido Enum, usuario_rh_id? nullable`). No `POST /rh/candidatos/{cid}/solicitacoes-assinatura`, se `etapas` vier vazio e o modelo tiver roteiro-padrão, ele é materializado (o RH só preenche os externos que faltam). CRUD dessas etapas-padrão junto do modelo em `app/api/modelos.py` (`_aplicar` passa a aceitar `etapas_padrao`).

### Signatário USUÁRIO RH assina logado (prova = senha revalidada)
- **`GET /rh/minhas-assinaturas`** (requer_rh) — etapas `tipo=usuario_rh`, `usuario_rh_id == eu`, na vez (`ordem==etapa_atual_ordem`), `assinado_em is null`, `status=aguardando`. É a fila "documentos aguardando MINHA assinatura".
- **`GET /rh/etapas/{etapa_id}/previa`** (requer_rh, dono da etapa) — PDF prévio do documento (reusa `_gerar_pdf`/`gerar_documento_modelo` a partir do snapshot da solicitação).
- **`POST /rh/etapas/{etapa_id}/assinar`** (requer_rh) — Body `{ senha }`. Revalida `verificar_senha(senha, usuario.senha_hash)` (prova de presença; 401 `senha_invalida` + rate-limit `exigir(f"assin-rh:{usuario.id}")`). Se ok e for a vez: grava `assinado_em/ip/user_agent/prova_metodo="senha_sessao_rh"`, calcula `hash_sha256` do doc parcial, gera+salva a via parcial (§5), chama `avancar_solicitacao`. Registra auditoria `etapa_assinada` ator=rh.
- **`POST /rh/etapas/{etapa_id}/recusar`** — Body `{motivo}` (§3).

### Signatário EXTERNO assina por link + OTP (espelha o candidato)
Rotas públicas (sem `requer_rh`), o token identifica a etapa:
- **`GET /assinar/{token}`** — resolve `token_hash` → `etapa_assinatura` (nova função `resolver_token_etapa` em `magic_link.py`, análoga a `resolver_token`). Retorna metadados: título do doc, papel, nome do signatário, se está na vez, se já assinou.
- **`GET /assinar/{token}/preview`** — PDF prévio.
- **`POST /assinar/{token}/solicitar-codigo`** (204, rate-limited) — gera OTP 6 dígitos, `otp_hash/otp_expira_em` na etapa, envia e-mail para `externo_email` (reusa `enviar_email` + `html_moderno`, TTL `otp_ttl_minutes`).
- **`POST /assinar/{token}/assinar`** — Body `{codigo}`. Valida OTP (mesma lógica de `assinar`: expirado 410, tentativas 429, incorreto 422). Se ok e na vez: grava evidências + `prova_metodo="otp_email"`, hash, gera+salva via parcial, `avancar_solicitacao`, e-mail de confirmação com a via anexa.

---

## 5. Geração do PDF

### 5.1. `pagina_manifesto` multi-assinante
Alterar a assinatura da função em `app/services/fichas.py`:
- Hoje: `pagina_manifesto(self, assinatura, candidato, cpf, base_url)` — UM assinante.
- Novo: aceitar **uma lista de "vistos"**. Introduzir um dataclass leve **`VistoAssinatura`** (`nome, papel, cpf, assinado_em, ip, hash_sha256, id_verificacao, metodo`) e:
  - `pagina_manifesto(self, vistos: list[VistoAssinatura], titulo, base_url)`.
  - Seção "Documento" (título + hash_final + id da solicitação) **uma vez**; depois **um bloco "Assinante N"** por visto, cada um com Nome/Papel/CPF mascarado-ou-cheio/Data(Brasília+UTC)/IP/user-agent/Método/Hash da via/**QR próprio para `/verificar/{id_verificacao}`** daquele signatário.
- Manter compatibilidade: um wrapper `pagina_manifesto_single(assinatura, candidato, cpf, base_url)` que monta uma lista de 1 `VistoAssinatura` e chama a nova — assim os `GERADORES` legados (fluxo do candidato sozinho) **não mudam**.

### 5.2. `bloco_assinatura` empilhado
- `bloco_assinatura` já existe e desenha 1 caixa. Para o PDF final, chamá-lo **em loop**, um por visto, com quebra de página quando `get_y() > self.h - 55` (já tem essa checagem). Ordenados por `ordem, assinado_em`.

### 5.3. Onde entra no gerador
- Documentos **de modelo**: `gerar_documento_modelo` passa a aceitar `vistos: list[VistoAssinatura] | None` em vez de só `assinatura`. Quando multi, empilha N blocos + manifesto com N QRs.
- Documentos **fixos** (as fichas/ofícios): hoje cada `GERADORES[...]` recebe `assinatura`. Para multi, o parâmetro `assinatura` vira opcionalmente `vistos`. Como quase todo documento fixo é assinado só pelo candidato, o caminho comum não muda; só quando há roteiro (ex.: uma testemunha da empresa também assina uma ficha) é que a lista tem >1.

### 5.4. Vias parciais vs final no MinIO
- **Via parcial de cada etapa** (evidência individual, imutável): `candidatos/{cid}/assinaturas/{solicitacao_id}/etapa-{ordem}-{etapa_id}.pdf` — o documento **com os blocos das etapas já assinadas até ali** + manifesto parcial. Guardar em `etapa.pdf_key`. Serve de prova de o-que-cada-um-viu-ao-assinar e alimenta o hash daquela etapa (hash calculado sobre o doc **sem** blocos, como hoje).
- **PDF final consolidado** (quando `status=concluida`): `candidatos/{cid}/assinaturas/{solicitacao_id}/final.pdf` — todos os blocos empilhados + manifesto com todos os vistos. Grava `solicitacao.pdf_final_key` + `hash_final_sha256`. É o que o dossiê (`app/services/dossie.py`) passa a incluir quando existir solicitação concluída (senão, mantém a `Assinatura.pdf_key` legada).
- Convenção coerente com a de hoje (`candidatos/{cid}/fichas/{chave}-{assinatura_id}.pdf`), mas em subpasta `assinaturas/` para não colidir e manter a via legada do candidato intocada.

---

## 6. Verificação pública multi-assinatura

- **Manter** `GET /verificar/{assinatura_id}` como está (retro-compat: QRs de PDFs antigos apontam para ele).
- **Nova** `GET /verificar-etapa/{etapa_id}` — resolve `etapa_assinatura`, devolve `{valida, documento, papel, assinante(mascarado), cpf(mascarado), assinado_em, hash_sha256, metodo}` e **também** um resumo do documento: `{solicitacao_id, total_etapas, etapas_assinadas, documento_concluido, coassinantes: [{papel, assinante_mascarado, assinado_em}]}` — para o verificador ver que o documento tem várias assinaturas e quantas faltam. Auditoria `etapa_verificada` ator=publico.
- Unificar via helper: fazer `verificar_assinatura` (legado) e `verificar_etapa` compartilharem os mascaradores `_nome_mascarado`/`_cpf_mascarado` já existentes. Para a etapa `tipo=candidato`, resolver nome/cpf pelo `Candidato` (como hoje); para `usuario_rh`, pelo `UsuarioRH.nome` (sem CPF, ou CPF só se cadastrado); para `externo`, por `externo_nome/externo_cpf`.
- Novos manifestos usarão `/verificar-etapa/{id}` nos QRs. Cada bloco/QR aponta para a etapa correspondente.

---

## 7. Frontend

`frontend/src/api.js` ganha as chamadas novas. CSS só em `styles.css`, reusando `.rh-tabela`, `.rh-metrica`, chips `--chip-cor`, `comAmpulheta()`, edição inline (convenções do CLAUDE.md).

### RH monta o roteiro (`src/rh/`)
- Na tela do colaborador, ao lado de "Enviar modelo", nova ação **"Coletar assinaturas"** que abre a montagem inline do roteiro: escolher documento (ficha fixa ou modelo aplicável), depois linhas de etapa (edição inline): papel (select dos `papeis-assinatura`), ordem, tipo (candidato / usuário RH [select de `UsuarioRH` ativos] / externo [nome+email+cpf opcional]). Botão "Disparar". Ação pesada → `comAmpulheta()`.
- Na edição de **modelo de documento**: seção "Roteiro padrão de assinatura" (papéis + ordem + tipo sugerido) — vira o default ao coletar.
- **Timeline** do documento: tabela `.rh-tabela` (vira card no mobile via `responsivo.js`) com papel/ordem/quem/status(chip: aguardando/assinado/recusado)/quando. Link para baixar via parcial e, quando concluída, o final.

### Usuário RH assina (fila)
- Item de menu/badge **"Aguardando minha assinatura"** consumindo `GET /rh/minhas-assinaturas`. Cada item: prévia (abre PDF) + botão "Assinar" que pede a **senha** num modal (prova de presença) → `POST /rh/etapas/{id}/assinar`. Sucesso remove da fila e mostra chip "Assinado".

### Página pública do signatário externo (`src/candidato/` ou nova rota pública)
- Rota `/assinar/{token}` — página enxuta espelhando o passo de assinatura do candidato: mostra doc (prévia), papel, botão "Receber código" → campo OTP → "Assinar". Reaproveitar componentes/estilos do wizard do candidato. Sem dados de terceiros além do necessário (só nome+doc). Estados: fora-da-vez ("aguardando assinaturas anteriores"), já-assinado, expirado, recusar.

### Glossário
- Novos termos ("roteiro de assinatura", "etapa", "signatário externo") explicados via `Ajuda.jsx` (não trocar por sinônimos — convenção).

---

## 8. LGPD (dados de terceiros)

- **Minimização:** de externos guardar só `nome`, `email`, `cpf` (opcional). CPF só se realmente for para o manifesto; se ausente, manifesto imprime "não informado". E-mail nunca vai ao verificador público (igual hoje).
- **Máscara no público:** `/verificar-etapa` mascara nome (`_nome_mascarado`) e CPF (`_cpf_mascarado`); nunca expõe e-mail/IP/user-agent (mantém a política atual do `verificar_assinatura`).
- **Base legal / finalidade:** dados do externo tratados unicamente para formalizar aquela assinatura; registrar no envio um `registrar(db,"etapa_externo_convidada",...)`.
- **Retenção:** ao cancelar/expirar sem assinar, um passo de limpeza zera `externo_email`/`externo_cpf`/`token_hash`/`otp_hash` da etapa não assinada após a retenção (reusar a política da lixeira, padrão 60 dias). Etapas **assinadas** preservam os dados (são prova do ato — necessidade de conservação).
- **Exclusão pela lixeira:** cancelar/excluir uma `solicitacao_assinatura` passa por `mandar_para_lixeira` antes do delete (convenção do projeto), com retenção configurável.
- **Auditoria:** todo ato (`etapa_assinada`, `etapa_recusada`, `solicitacao_cancelada`, `etapa_verificada`, `codigo_etapa_solicitado`) via `app/services/auditoria.registrar`, com ator e detalhe.

---

## 9. Riscos e casos-limite

- **Dado do documento muda depois de alguém já ter assinado:** hoje `Assinatura` tem `invalidada_em`. Replicar: se o RH edita dados que aparecem no doc, `invalidar_solicitacao` marca a solicitação e cada etapa como invalidada, `/verificar-etapa` responde `substituida`, e um **novo** roteiro é criado do zero (não reabrir etapas parciais — assinaturas anteriores valiam para o texto antigo). O snapshot `titulo_doc/corpo_doc` na solicitação protege documentos de modelo de edições do modelo.
- **Usuário RH signatário sai do RH (inativado) no meio do fluxo:** `requer_rh` já bloqueia inativo. A etapa fica travada → o RH pode **reatribuir** a etapa (`POST /rh/etapas/{id}/reatribuir` com novo `usuario_rh_id` ou converter para externo) enquanto `assinado_em is null`. Não permitir reatribuir etapa já assinada.
- **Reenvio/duplicação:** `disparar` é idempotente por estado (só sai de `rascunho`→`aguardando`); reenviar código é rate-limited (`exigir`); reusar pendência ativa como `enviar_para_pessoa` já faz.
- **Ordem com empate (paralelo):** etapas de mesma `ordem` assinam em qualquer sequência; `avancar_solicitacao` só sobe quando **todas** dessa ordem concluem — cuidar de corrida com `SELECT ... FOR UPDATE` na solicitação ao promover etapa (evitar dois callbacks concluírem simultaneamente e pularem ordem).
- **Candidato é signatário mas o link mágico expira:** o e-mail de código do candidato usa o fluxo atual; se o `AcessoMagico` expirou, o RH reemite link (já existe). A etapa do candidato continua pendente até ele assinar.
- **Verificador de PDF antigo:** QRs antigos (`/verificar/{assinatura_id}`) continuam funcionando — nada de quebra.
- **fpdf2 (armadilha conhecida):** blocos empilhados e manifesto multi-assinante geram muito conteúdo → validar `add_page()` entre blocos e `new_x/new_y` nos `multi_cell`. **Prova visual obrigatória** de um PDF final com ≥3 signatários (tool Read no PDF).

---

## 10. Sequência de implementação incremental

1. **Migração + modelos** (`solicitacao_assinatura`, `etapa_assinatura`, enums, `modelo_etapa_padrao`) + `roteiro_assinatura.py` com `avancar_solicitacao`/`tem_roteiro`. Sem endpoints ainda. Alembic `upgrade head` limpo.
2. **PDF multi-assinante isolado:** `VistoAssinatura`, `pagina_manifesto` refeita + `pagina_manifesto_single` wrapper, `bloco_assinatura` em loop, `gerar_documento_modelo(vistos=...)`. **Prova visual.** Nada muda para o candidato (wrapper) → smoke 15/15 continua verde. **Já entrega valor:** base sólida sem risco.
3. **Roteiro só com USUÁRIOS RH** (o caso mais simples, sem token/OTP novo): endpoints de montar/disparar/cancelar + `GET /rh/minhas-assinaturas` + `POST /rh/etapas/{id}/assinar` (senha) + hook do candidato (`promover_etapa_do_candidato`). Front: montar roteiro + fila do RH. Fluxo candidato→testemunha-interna→contratante já funciona ponta a ponta. **Primeiro valor real de multi-signatário.**
4. **Signatário EXTERNO:** `resolver_token_etapa`, rotas públicas `/assinar/{token}/*` (preview, solicitar-código, assinar), e-mails, página pública. `/verificar-etapa`. Front público.
5. **Roteiro-padrão no modelo** (`modelo_etapa_padrao` + UI) e **reenvio/reatribuição/expiração** (worker) + limpeza LGPD de dados de externos não assinados.
6. **Dossiê** passa a preferir o `pdf_final_key` da solicitação concluída; exportações refletem status. `CLAUDE.md` atualizado ao fim da leva (rotina de memória).

Cada passo fecha com: banco efêmero recriado limpo + `smoke_test.py` 15/15 + `npm run build` + prova visual de PDF; commit `feat(vX.Y): ...` no `main` e acompanhar o CI.

---

**Arquivos-chave a criar:** `backend/app/models/solicitacao_assinatura.py`, `backend/app/services/roteiro_assinatura.py`, `backend/app/api/solicitacoes_assinatura.py`, migração em `backend/alembic/versions/`, front em `frontend/src/rh/` (montagem + fila) e página pública `/assinar/{token}`.
**Arquivos-chave a alterar:** `backend/app/services/fichas.py` (manifesto/bloco multi), `backend/app/api/assinaturas.py` (hook pós-assinatura do candidato + `verificar-etapa`), `backend/app/api/modelos.py` (roteiro-padrão), `backend/app/models/modelo_documento.py` (etapas-padrão), `backend/app/services/magic_link.py` (`resolver_token_etapa`), `backend/app/services/dossie.py` (preferir PDF final), `backend/app/main.py` (montar router), `frontend/src/api.js`, `frontend/src/styles.css`, `frontend/src/rh/Ajuda.jsx`.

---

# Crítica adversária — Plano Multi-Signatário

Revisei o plano contra o código real (`assinaturas.py`, `magic_link.py`, `models/assinatura.py`, `limite.py`, `modelos.py`, `fichas.py`). O plano é competente e a decisão de camada (não reescrever `Assinatura`) é correta. Mas há **furos concretos** — alguns críticos — que precisam entrar no plano antes de escrever qualquer linha.

## CRÍTICOS

### C1. O reuso da `Assinatura` do candidato colide com `_registro` e com o modelo — a etapa do candidato pode nunca disparar, ou disparar no documento errado
**Por que quebra.** O plano diz: para `tipo=candidato`, ligar `etapa.assinatura_id` à `Assinatura` existente e, num hook pós-assinatura, "promover" a etapa. Mas:
- `_registro(db, candidato, documento)` (linha 35-48) faz **dedup por `(candidato_id, documento, invalidada_em IS NULL)`**. Se o RH monta um roteiro para `termo_vt` e o candidato **já tinha** uma `Assinatura` de `termo_vt` assinada por fora do roteiro (fluxo normal do wizard), o hook nunca cria a etapa — ou pior, encontra uma `Assinatura` **já assinada** e a etapa é "promovida" instantaneamente sem que o roteiro tenha sido observado. Ordem quebrada.
- Para documento de **modelo**, o `enviar_para_pessoa` já cria **uma** `Assinatura` com `papel = m.papel_assinatura` (linha 205-208). O roteiro cria **outra** solicitação com snapshot próprio. Agora existem duas fontes de verdade para o mesmo documento de modelo do mesmo candidato, e `_assinaturas_modelo` (linha 69) vai listar a Assinatura órfã no wizard do candidato **fora** do controle do roteiro.
- O candidato assina via `assinar_todos`, que assina **TODAS** as pendentes de uma vez com um único OTP (linha 298-311). Se o roteiro exige que o candidato seja a **ordem 3**, não há como impedir que `assinar_todos` assine a `Assinatura` ligada à etapa dele **antes da vez** — o endpoint do candidato "nem sabe que existe roteiro" (é premissa do próprio plano), então não respeita `etapa_atual_ordem`.

**Correção concreta.**
- A etapa `tipo=candidato` **não deve** reusar a `Assinatura` de fluxo livre. O roteiro deve criar uma `Assinatura` **dedicada e marcada** (nova coluna `solicitacao_etapa_id` na `Assinatura`, ou um flag `origem_roteiro=True`), e `_registro`/`_docs_exigidos`/`_assinaturas_modelo` devem **excluir** Assinaturas de roteiro do fluxo livre (`WHERE solicitacao_etapa_id IS NULL`). Sem isso o wizard do candidato e o roteiro brigam pela mesma linha.
- O gate de ordem tem de ser aplicado **no ponto de assinatura do candidato** quando a Assinatura pertence a um roteiro: em `assinar`/`assinar_todos`, filtrar pendentes cuja etapa esteja `fora_da_vez`. Isso **contradiz** a premissa "não tocar no fluxo do candidato" — decida explicitamente: ou o candidato só assina roteiro por um caminho separado, ou o fluxo dele passa a consultar `tem_roteiro`. O plano finge que dá para ter os dois; não dá.

### C2. Link mágico do externo herda um defeito do `resolver_token`: **não é single-use** e o `token` completo trafega em rota GET
**Por que quebra.** `resolver_token` (magic_link.py, linha 32-41) marca `usado_em` mas **continua válido até expirar** — é reutilizável. O plano diz "espelhar o candidato" e clonar em `resolver_token_etapa`. Para o candidato isso é aceitável (é o titular dos próprios dados). Para um **signatário externo** (testemunha, contratante de outra empresa), um link reutilizável significa: qualquer um com o link (encaminhado, vazado em histórico de e-mail, logado em proxy) **abre a página de assinatura de dados de terceiros e pode disparar/assinar** com o OTP que chega no e-mail do externo. Pior: as rotas `GET /assinar/{token}` e `GET /assinar/{token}/preview` expõem o **PDF com dados pessoais** só com o token na URL — URLs vazam em Referer, logs de servidor e histórico.

**Correção concreta.**
- Token do externo **single-use por sessão de assinatura**: ao concluir (assinado/recusado), revogar (`token_hash=NULL` ou `revogado=True`). Após `assinado_em`, `/assinar/{token}` só mostra "já assinado", nunca o PDF de novo.
- O **PDF/preview** do externo **exige o OTP validado** (uma sessão curta), não só o token. O token abre a página; ver o documento com dados pessoais exige o 2º fator — mesma lógica LGPD que já existe no portal (dados só após 2FA).
- OTP de uso único **de verdade**: hoje o candidato zera `otp_hash` ao assinar (linha 458), mas entre solicitar e assinar o mesmo código funciona N vezes. Para o externo, adote **lockout persistente** (a etapa já terá `otp_tentativas`) e invalide o `otp_hash` **em qualquer** desfecho.

### C3. `avancar_solicitacao` + rate-limit + hook: corrida real de **etapa liberada/assinada duas vezes**
**Por que quebra.** O plano cita `SELECT ... FOR UPDATE` "ao promover" para o caso de empate de ordem. Mas o problema é mais amplo:
- O hook do candidato roda dentro de `assinar_todos`, que já faz `db.commit()` no meio do loop de documentos. Dois cliques do candidato (duplo submit) ou um retry HTTP disparam **dois** `avancar_solicitacao` concorrentes.
- `limite.py` é **in-memory e reseta no restart do container** (é dito no próprio arquivo). O plano apoia toda a proteção anti-replay/anti-flood do externo em `exigir(...)`. Num deploy com re-pull da imagem (Portainer, como diz o CLAUDE.md) **ou múltiplos workers**, o rate-limit **não é compartilhado** — cada réplica/restart zera. Não serve como barreira de consistência, só de conforto.

**Correção concreta.**
- `avancar_solicitacao` deve ser **idempotente e serializada**: `SELECT ... FOR UPDATE` na `solicitacao_assinatura` **no início** (não só no empate), rechecar o estado, e só então promover. Toda transição de estado (`aguardando→concluida`, subir `etapa_atual_ordem`) sob esse lock.
- A assinatura de cada etapa precisa de **guarda de idempotência**: `UPDATE etapa SET assinado_em=now() WHERE id=? AND assinado_em IS NULL` e checar `rowcount` — se 0, já estava assinada, aborta silenciosamente. Não confie no rate-limit para impedir dupla-assinatura.
- Não descreva o rate-limit como barreira de segurança. Ou é aceito como best-effort (documentar) ou vira Redis (já há Redis no stack, CLAUDE.md).

### C4. Prova do usuário RH por "senha da sessão" é fraca como evidência jurídica e cria superfície de brute-force
**Por que quebra.** O plano usa `verificar_senha(senha, usuario.senha_hash)` como "prova de presença". Problemas: (a) o usuário **já está logado** (Bearer de sessão) — revalidar a mesma senha não prova mais nada além de "sabe a própria senha"; um admin com acesso ao token de sessão de outro RH poderia assinar no lugar dele se souber/resetar a senha; (b) `exigir(f"assin-rh:{id}")` é o mesmo rate-limit in-memory frágil do C3; (c) não há segundo fator — enquanto o candidato e o externo têm OTP, o RH tem só a senha. Decisão do Bruno foi "senha da sessão como prova, sem OTP", então **não é para trocar**, mas o plano precisa fechar os buracos.

**Correção concreta.**
- Registrar na etapa **qual sessão/usuário** assinou (id do `UsuarioRH` **e** o hash do token de sessão ou seu id), `ip`, `user_agent`, e `prova_metodo="senha_sessao_rh"` — o plano já prevê parte, mas garanta que o **id do usuário logado == `etapa.usuario_rh_id`** (senão 403; um RH não assina a etapa de outro RH mesmo sabendo a senha alheia por acaso).
- Lockout **persistente** por usuário após N senhas erradas (coluna na etapa ou tabela de tentativas), não só o rate-limit volátil.
- Deixar explícito no manifesto que a prova do interno é "autenticação da conta corporativa + reautenticação por senha" (art. 4º, I/II da 14.063) — o texto jurídico do bloco muda por tipo de signatário.

## MÉDIOS

### M5. `papel` como snapshot String está certo, mas o **QR por etapa** exige nome/CPF resolvidos no ato da assinatura, não na verificação
**Por que.** O plano resolve nome/CPF do externo por `externo_nome/externo_cpf` e do candidato pelo `Candidato` **na hora de `/verificar-etapa`**. Mas o `Candidato` pode ter mudado de nome/CPF entre a assinatura e a verificação (correção de cadastro). Hoje isso já é um risco no `verificar_assinatura` (resolve `doc_id.cpf` atual — linha 210/224), mas multiplicar por N assinantes agrava. A via assinada mostra um nome; o verificador pode mostrar outro.
**Correção.** Snapshot de `assinante_nome` e `assinante_cpf` **na etapa**, gravados no momento de `assinado_em`. `/verificar-etapa` lê o snapshot mascarado, não o registro vivo. (Considerar retrofit também no `verificar_assinatura` legado, mas fora de escopo.)

### M6. Recusa "cancela a solicitação inteira" perde o trabalho já feito e não trata reabertura
**Por que.** All-or-nothing: uma testemunha recusa → `status=cancelada`, e o plano manda "criar novo roteiro do zero". As etapas já assinadas (ex.: candidato + contratante) viram lixo e teriam de reassinar — atrito real e desperdício de assinaturas válidas.
**Correção.** Separar **recusa** de **cancelamento**: recusa marca a etapa `recusada` e coloca a solicitação em `pendente_rh` (não `cancelada`); o RH decide reatribuir **só aquela etapa** (o plano já tem `reatribuir` para RH inativo — estenda a externos) sem invalidar as etapas anteriores, **desde que o documento não tenha mudado**. Só se o texto mudar é que invalida tudo (C1/§9 do plano).

### M7. Envio de e-mail dentro da transação de assinatura pode assinar e não notificar (ou vice-versa)
**Por que.** No código atual `enviar_email` é chamado **após** `db.commit()` (linha 356/361) — bom. Mas `avancar_solicitacao` do plano "dispara notificação de cada signatário da ordem" **dentro** do fluxo de promoção, que roda dentro do `assinar`. Se o e-mail falha (SMTP fora), ou a transação faz rollback depois do e-mail, o estado e as notificações divergem (o próximo assinante recebe link mas o commit não persistiu; ou assina e ninguém é avisado).
**Correção.** Enfileirar notificações (RQ, já existe) **após commit**, ou coletar os destinatários e disparar fora da transação, com retry. Nunca `enviar_email` sob o lock `FOR UPDATE` do C3 (segura a linha durante I/O de rede).

### M8. `/verificar-etapa` vaza a existência e composição do roteiro a quem tem só um QR
**Por que.** O plano faz `/verificar-etapa/{id}` devolver `coassinantes: [{papel, assinante_mascarado, assinado_em}]` e `total_etapas`. Quem escaneia o QR de **uma** via (ex.: a testemunha externa) passa a ver **quem mais** assinou (nome mascarado do contratante, do candidato). É mais exposição de terceiros do que o `verificar_assinatura` atual (que mostra só o próprio assinante).
**Correção.** No público, devolver **apenas o assinante daquela etapa** + um booleano `documento_concluido` e a **contagem** (`X de N assinaturas`). Não listar `coassinantes` nominalmente no endpoint público. A timeline nominal fica no painel RH autenticado.

### M9. `modelo_etapa_padrao` com `usuario_rh_id` fixo apodrece
**Por que.** Roteiro-padrão do modelo guardando `usuario_rh_id` (o plano permite) congela uma pessoa; quando ela sai, todo modelo aponta para um RH inativo e todo disparo nasce travado.
**Correção.** Roteiro-padrão guarda **só papel + ordem + tipo_sugerido**. Se `tipo_sugerido=usuario_rh`, a pessoa é escolhida **no disparo**, nunca no modelo. Remover `usuario_rh_id` da `modelo_etapa_padrao`.

## MENORES

- **m10. Comparação de OTP não é constant-time.** O código atual usa `hashlib.sha256(...).hexdigest() != otp_hash` (linha 320/447). Ao replicar para o externo, use `secrets.compare_digest` nos hashes. (Baixa exploração real por serem hashes, mas é gratuito e o repo é público — alguém vai apontar.)
- **m11. Chave de MinIO por etapa usa `ordem` no nome** (`etapa-{ordem}-{etapa_id}.pdf`). Ordem pode empatar (paralelo) → dois arquivos `etapa-2-*`. O `etapa_id` no fim salva de colisão, mas tirar `ordem` do path evita confusão. Menor.
- **m12. Expiração deixa vias parciais "válidas" mas documento não concluído** — o plano assume isso ok. Garanta que `/verificar-etapa` de uma via parcial de solicitação **expirada** diga claramente "assinatura individual válida; documento não foi concluído", senão um contratante que assinou pensa que o contrato existe.
- **m13. `criada_por` como String(120) do e-mail** — ok, mas registre também via `auditoria` (já previsto). Coerente com o resto.
- **m14. Downgrade da migração** dropa enums com `checkfirst=True` — cuidado se `documento_assinavel` for compartilhado: **nunca** dropar `documento_assinavel` no downgrade (ele é da `Assinatura` legada). Só dropar `status_solicitacao` e `tipo_signatario`. O plano não é explícito nisso.

---

# LISTA DE CORREÇÕES OBRIGATÓRIAS (antes de implementar)

1. **(C1)** Assinaturas de roteiro do candidato são **dedicadas e marcadas** (`solicitacao_etapa_id`/flag na `Assinatura`); `_registro`, `_docs_exigidos`, `_assinaturas_modelo` passam a filtrar `origem_roteiro IS NULL`. Nunca reusar a `Assinatura` de fluxo livre.
2. **(C1)** Aplicar **gate de ordem no ponto de assinatura do candidato**: `assinar`/`assinar_todos` pulam pendentes cuja etapa esteja `fora_da_vez`. Assumir e documentar que o fluxo do candidato **passa a consultar `tem_roteiro`** (a premissa "não tocar" cai para documentos em roteiro).
3. **(C2)** Token do externo **single-use** (revogar em assinado/recusado); `/assinar/{token}` nunca reexibe o PDF após concluído.
4. **(C2)** **PDF/preview do externo só após OTP validado** (2º fator), não só com o token na URL. Alinhar à política "dados após 2FA" do portal.
5. **(C2/C4)** OTP e senha de uso único **de verdade** + **lockout persistente** (coluna na etapa), invalidando o segredo em qualquer desfecho. Não depender do rate-limit in-memory.
6. **(C3)** `avancar_solicitacao` **serializada com `SELECT ... FOR UPDATE`** na solicitação desde o início; toda transição idempotente.
7. **(C3)** Assinatura de etapa com **guarda idempotente** (`UPDATE ... WHERE assinado_em IS NULL` + checar `rowcount`); dupla-assinatura impossível independentemente do rate-limit.
8. **(C4)** Etapa `usuario_rh`: exigir **`usuario_logado.id == etapa.usuario_rh_id`** (403 caso contrário) + gravar id da sessão/usuário, ip, ua; texto jurídico do manifesto por tipo de signatário.
9. **(M5)** Snapshot de **`assinante_nome`/`assinante_cpf` na etapa** no ato da assinatura; `/verificar-etapa` lê o snapshot.
10. **(M6)** Separar **recusa** de **cancelamento**: recusa → `pendente_rh` + reatribuição da etapa única, sem invalidar etapas já assinadas (a menos que o documento mude).
11. **(M7)** Notificações **fora da transação** (após commit / via RQ); nenhum `enviar_email` sob o lock.
12. **(M8)** `/verificar-etapa` público mostra **só o assinante daquela etapa** + `X de N` + `documento_concluido`; **sem lista nominal de coassinantes**.
13. **(M9)** `modelo_etapa_padrao` guarda **só papel/ordem/tipo_sugerido** — sem `usuario_rh_id`.
14. **(m10/m14)** `secrets.compare_digest` na checagem de OTP; downgrade da migração **não** dropa `documento_assinavel` (só os dois enums novos), enums novos com `create(checkfirst=True)` / `create_type=False` nas colunas (armadilha conhecida do projeto).

**Requisitos do Bruno — status:** ordem por papel (ok, com C1/C3), interno assina logado por senha (ok, com C4/#8), externo por link+OTP (ok, com C2/#3-5), candidato assina como hoje (**parcialmente atendido** — a premissa "sem tocar no fluxo dele" é incompatível com ordem quando o candidato não é o 1º; #2 resolve isso explicitando a mudança). Sem essas 14 correções, o plano tem furo de consistência (C1/C3) e de LGPD/segurança de terceiros (C2/M8) que se manifestam já no primeiro roteiro com externo.