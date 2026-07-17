# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/) · versionamento semântico.

Rollback: toda migration tem `downgrade()` escrito para não destruir dados —
`alembic downgrade -1` volta uma revisão; o código volta apontando a stack para a
tag anterior da imagem no GHCR. Faça `pg_dump` antes de qualquer downgrade.

## [1.15.0] — 2026-07-17

### Adicionado
- **Banco de Talentos**: formulário **público** (`/banco-de-talentos`, também
  linkado no portal) onde interessados deixam nome, contato, cargo pretendido,
  cidade, escolaridade e uma apresentação — protegido por honeypot anti-spam.
  No painel, uma aba **Banco de Talentos** lista os cadastros com filtros
  (status, cargo, busca livre), triagem de status e o botão **Converter em
  candidato**, que cria o cadastro migrando os dados já preenchidos, dispara o
  link de admissão e abre a ficha do novo candidato.

## [1.14.0] — 2026-07-17

### Adicionado
- **Módulo de criação de documentos (CRUD)**: o RH cria/edita documentos do
  zero em Configurações, já no papel timbrado padrão, com **variáveis
  dinâmicas** (`{{nome}}`, `{{cpf}}`, `{{cargo}}`, `{{posto}}`, `{{salario}}`,
  `{{data}}`…). Cada modelo pode ser vinculado a **qualquer colaborador**, a um
  **cargo** ou a um **posto**; na tela do colaborador aparecem os modelos
  aplicáveis com um botão **Gerar** (PDF preenchido no timbrado). Prévia
  disponível com os placeholders visíveis.
- **Todo PDF enviado vai para o papel timbrado A4** (decisão do RH): cada
  página do original é reduzida proporcionalmente e centralizada no corpo da
  página timbrada, sem distorcer. A leitura de texto (OCR e data do
  comprovante) passou a usar sempre o PDF original.

### Alterado
- Raiz do sistema virou um **portal com três portas** (Sou Candidato / Sou RH /
  Verificar documento) e há uma **entrada pública de verificação** (`/verificar`)
  onde se digita o código do registro.

## [1.12.0] — 2026-07-17

### Adicionado
- **Cargo, salário base e adicionais na ficha de cadastro**: o RH digita o
  salário à mão (texto livre) e adiciona quantos adicionais quiser (nome +
  valor em R$ ou %) na tela do posto; tudo passa a constar automaticamente na
  Ficha Cadastral do Colaborador. Alterar cargo/salário/adicionais de uma
  ficha já assinada a reabre para o colaborador assinar a versão atualizada
  (invalidação historizada, nunca deleção).
- **Colaborador troca a opção pelo Vale-Transporte** direto na tela de
  assinatura, enquanto o Termo de VT não foi assinado; depois de assinado, a
  troca é bloqueada (exigiria nova assinatura).

### Alterado
- **Marca d'água "GREENHOUSE"** (arte oficial que existia mas não era usada)
  agora aparece esmaecida na borda direita de todos os PDFs timbrados: fichas,
  ofícios, manifesto e páginas geradas a partir de fotos recebidas.

### Infraestrutura
- Os dois workflows de CI viraram um só (`ci.yml`, jobs `imagens` +
  `testes-de-interface`): cada commit aparece uma vez na lista de Actions.

## [1.10.0] — 2026-07-17

### Adicionado
- **Envio de e-mail via Power Automate (webhook)** como caminho "plug and play"
  para locatários do Microsoft 365 em que o admin bloqueia SMTP autenticado e
  registro de aplicativo: o RH cola a URL de um fluxo HTTP e o sistema manda o
  e-mail em JSON (com anexos em base64) para ele. Entra na cadeia de envio como
  Microsoft 365 → Google → **Power Automate** → SMTP, com card próprio no painel
  (passo a passo do fluxo e teste de envio). O envio OAuth direto via Microsoft
  Graph já existia e continua sendo a opção recomendada.

## [1.9.0] — 2026-07-17

### Adicionado
- **Frente e verso à prova de falhas**: nos documentos de duas partes (RG,
  reservista, CNH) o envio é passo a passo, um arquivo por vez — o seletor perde
  a seleção múltipla, acabando com o erro de quem tentava mandar os dois juntos.
- **Editor de imagem** (sem bibliotecas externas, para não pesar no aparelho de
  quem tem pouca internet): recorte com folga de segurança de 18% além da
  moldura já usada para alinhar, cantos arrastáveis (mouse e toque) e rotação de
  90° para a foto que saiu deitada. Vale para a foto tirada e para a imagem
  enviada do aparelho. Botão "Voltar" claro na câmera e no editor.

## [1.8.0] — 2026-07-17

### Corrigido
- **PDF não abria no Chrome do Android** (fundo escuro com um botão "Abrir" sem
  ação): o RH passa a ver os documentos por um visualizador em canvas (pdf.js)
  **apenas no celular** — no desktop segue o visualizador nativo do navegador.
- **Erros de upload** deixavam de virar um "sem conexão" genérico: queda real de
  rede, arquivo grande demais (413), formato inválido e erro de validação agora
  têm mensagens próprias e específicas.
- **Cabeçalho timbrado** dos documentos: arte alinhada à direita e título do
  documento centralizado.

## [1.7.0] — 2026-07-16

### Adicionado
- **Acordo de Confidencialidade** como quarta ficha de todo candidato,
  **retroativo**: quem ainda não assinou (mesmo já aprovado) passa a dever a
  assinatura automaticamente — o link de sempre abre direto na tela de
  assinar, e o dossiê passa a incluí-lo. Texto do modelo oficial com
  qualificação puxada dinamicamente da ficha (nome, CPF, nome social, função),
  endereço da sede unificado com o do rodapé, formatação uniforme no papel
  timbrado e gramática revisada (concordâncias, vírgulas, "resultará").

### Alterado
- OCR com IA (Mistral) passou a ser o **primeiro** degrau da leitura para
  qualquer arquivo (antes: só quando o PDF não tinha camada de texto);
  fallback: camada de texto do PDF → Tesseract local.

### Corrigido
- Busca no relatório de colaboradores quebrava (erro 500) quando havia
  candidato sem e-mail — efeito colateral do convite sem e-mail da 1.3.

## [1.6.0] — 2026-07-15

### Adicionado
- **Papel timbrado da empresa em todos os PDFs**: fichas, ofícios e manifesto
  usam as artes oficiais (cabeçalho de canto + rodapé institucional extraídos
  do modelo Word); fotos de documentos recebidos (RG, CPF…) viram página A4
  timbrada com o nome do documento e a data de recebimento. PDFs emitidos por
  órgãos (CTPS, certidões) seguem intactos — não se altera documento de
  terceiro. Vias já assinadas não mudam (hash preservado).
- **OCR com IA (Mistral)**: chave configurável pelo painel (com teste de
  leitura), cadeia de qualidade camada de texto do PDF → Mistral OCR →
  Tesseract local; falha de qualquer degrau cai para o seguinte em silêncio.
  Telemetria registra apenas tipo, hash e tamanho — nunca o conteúdo; a chave
  não aparece em logs; o aviso de privacidade do candidato passou a mencionar
  a leitura assistida por IA. PDFs escaneados (sem camada de texto) agora
  também são lidos quando a IA está ativa.

## [1.5.0] — 2026-07-15

### Adicionado
- **Fichas e assinaturas visíveis no painel**: o detalhe do candidato mostra
  cada documento exigido com o estado (assinado/aguardando), alerta quando o
  formulário está incompleto (fichas sairiam vazias) e ganhou o botão
  **"Notificar pendências por e-mail"** — cobrança com a lista exata do que
  falta e link novo. Nasceu de incidente real: e-mail cadastrado depois, e a
  pessoa nunca soube que havia fichas para preencher e assinar.
- **Termo de Consentimento LGPD (credenciamento)** no kit INFRAERO: gerado e
  assinado junto com os demais documentos do posto, com o mesmo código único.
- Painel do RH com **sidebar esquerda retrátil**, **barra de atividade** e
  botões travados durante requisições (fim do clique repetido); frases de
  espera agora também no painel.
- **Flash (torch)** na câmera guiada, quando o aparelho suporta.
- Foto OU arquivo para **todos** os documentos (fim do atalho que mandava
  CTPS/PIS direto ao seletor).
- Responsividade do painel para celular e tablet (tabelas com rolagem
  própria, revisão empilhada, métricas em grade).
- README rico (dores → soluções, rollback, resumo em inglês), CHANGELOG
  completo e LICENSE MIT.

### Alterado
- Salvar e-mail no contato avisa explicitamente que **não** envia nada
  sozinho — a notificação é um ato separado e auditado.

## [1.4.0] — 2026-07-15

Três fases nascidas de 11 anotações de uso real em produção, priorizadas em
mesa-redonda com foco em auditoria, LGPD e integridade das assinaturas.

### Adicionado
- **Fase 1 — controle do candidato:** ver o próprio envio (PDF), excluir envio
  ainda não aprovado e reenviar; preview de conferência da foto antes do envio;
  aviso de ciência do cartão de mobilidade (GO) com carimbo de data imutável;
  contrato do posto exibido a partir do cadastro (nada digitado à mão).
- **Fase 2 — poderes manuais do RH:** inserção de documento recebido fora do
  sistema (WhatsApp/e-mail/presencial) com etiqueta de origem; reabertura de
  status com motivo obrigatório; correção de dados da ficha por seção com
  auditoria campo a campo (antes → depois) e **re-assinatura granular** — só os
  documentos onde o dado aparece são invalidados e voltam para o candidato.
- **Fase 3 — frente e verso:** envio multi-arquivo vira um único PDF por
  documento; câmera guiada captura frente e verso em sequência (com passo
  opcional); OCR lê o texto combinado das partes.
- Assinaturas invalidadas são historizadas (nunca apagadas): o verificador
  público responde "assinatura substituída" com data e hash da via antiga; cada
  via assinada tem arquivo próprio no storage.
- E-mail/celular do candidato editáveis pelo RH e pelo próprio candidato, com
  trilha antes → depois na auditoria.
- Painel do RH com **sidebar esquerda retrátil**, barra de atividade global e
  botões travados durante requisições (fim do clique repetido).
- Captura por **foto OU arquivo para todos os documentos** (inclusive CTPS/PIS
  digitais — há quem tenha o cartão físico na mão).

### Alterado
- Comprovante de escolaridade passou a ser opcional.
- Câmera guiada sem disparo automático: o botão habilita quando o quadro está
  bom, mas quem fotografa é a pessoa; medidas de luz/foco restritas à moldura,
  com detecção de presença do documento.
- Exclusão/rejeição/substituição de arquivo varre todos os arquivos do slot
  (frente, verso, PDF) — cada um com hash SHA-256 na auditoria antes de sair.

### Corrigido
- Câmera dizia "tudo certo" com o documento fora do enquadramento (as medidas
  eram da cena inteira, não da moldura).

## [1.3.0] — 2026-07-15

### Adicionado
- Convite sem e-mail (só o nome é obrigatório): link em destaque para copiar e
  mandar pelo WhatsApp; e-mail vira pendência da ficha (o código de assinatura
  chega por ele).
- Leitor de identidade aceita **RG ou CNH**: detecta qual é, guarda no slot
  certo e avisa com gentileza quando a CNH veio no lugar do RG.
- OCR estendido: CNH (registro/categoria), título de eleitor (número/zona/
  seção), documento de CPF e CEP de comprovante de endereço; sugestões
  aplicadas **só com consentimento explícito** e nunca sobre campos preenchidos.
- Recusa imediata de documento de CPF com número divergente da ficha.
- **Câmera guiada** com moldura por tipo de documento, dicas em tempo real de
  luz/foco/enquadramento e conferência da foto; leitores junto aos campos que
  preenchem (RG/CNH na etapa de dados, comprovante na etapa de endereço, com
  moldura focada no cabeçalho da conta).
- Olhinho (mostrar/ocultar) em todos os campos de senha e segredos.
- Tema claro/escuro seguindo o dispositivo, com troca manual.
- Testes Playwright no CI contra a stack completa, incluindo a câmera (fake
  device do Chromium).

## [1.2.0] — 2026-07-14/15

### Adicionado
- Validações inteligentes no upload: foto tremida/borrada recusada na hora
  (variância do Laplaciano) e comprovante de endereço com mais de 90 dias
  bloqueado com mensagem clara.
- **Manifesto de assinatura** gravado como última página de cada PDF assinado:
  hash SHA-256, ID do registro, assinante, datas (Brasília + UTC), IP real,
  dispositivo, método e modalidade legal — com QR code para o **verificador
  público** (`/verificar/<id>`), que exibe dados minimizados (LGPD).
- Portal único de retorno **/entrar**: CPF + 2 perguntas de verificação
  derivadas da própria ficha (estilo TSE), com anti-enumeração, lockout e
  fallback de link por e-mail.
- Relatório de colaboradores com filtros e exportação **Excel** (~49 colunas).
- **Postos de serviço** com documentos específicos por contrato (ex.: ofícios
  INFRAERO) gerados em PDF fiel ao layout oficial e assinados na plataforma;
  assinantes dos documentos editáveis pelo painel.
- Nome social (Decreto 8.727/2016) e filiação (pai omitível) na ficha e nos
  documentos.
- Repaginada visual "fintech": fonte própria, cores vibrantes, micro-animações
  (com respeito a `prefers-reduced-motion`); máscara de datas `dd/mm/aaaa`
  digitável (o público trava no date picker).
- Botão "copiar link" por candidato no painel (para WhatsApp, sem reenviar
  e-mail).

## [1.1.0] — 2026-07-14

Primeira versão em produção (VPS via Portainer) + melhorias da v1.1.

### Adicionado
- Validação de CPF com dígito verificador (algoritmo da Receita) no backend e no
  formulário (aviso imediato + máscara), para titular e dependentes.
- Dashboard de métricas no painel do RH: candidatos, em andamento, documentos
  aguardando revisão, reenvios pendentes, dossiês gerados e tempo médio até o dossiê.
- "Esqueci minha senha" na tela de login: link por e-mail válido por 30 minutos e de
  uso único.
- Gestão da equipe do RH pelo painel: criar usuários (com e-mail de boas-vindas),
  editar, redefinir senha e ativar/desativar (com proteções contra auto-bloqueio).
- Envio de e-mail com "Fazer login com o Google" (OAuth + Gmail API), além do
  Microsoft 365; prioridade M365 → Google → SMTP.
- Teste de SMTP com diagnóstico dirigido (mostra a resposta exata do servidor e o
  passo de correção para os casos comuns do Microsoft 365).

### Corrigido
- Página em branco ao abrir um candidato no painel (hook condicional no React).
- Aprovar/rejeitar em massa não funcionavam (ordem de rotas no FastAPI); erros das
  ações em massa agora sempre aparecem na tela.
- Links gerados (link mágico, reset, e-mails, callback OAuth) agora derivam do endereço
  público da própria requisição — funcionam em localhost, IP:porta e domínio sem
  configurar BASE_URL; nginx preserva a porta.

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

[1.7.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.7.0
[1.6.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.6.0
[1.5.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.5.0
[1.4.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.4.0
[1.3.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.3.0
[1.2.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.2.0
[1.1.0]: https://github.com/fontesmidias/admissao/releases/tag/v1.1.0
[1.0.0-rc.1]: https://github.com/fontesmidias/admissao/releases/tag/v1.0.0-rc.1
