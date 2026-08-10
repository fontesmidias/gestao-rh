# Componentes do painel — descrição e regras próprias

Carrega quando se trabalha sob `frontend/src/rh/`. Saiu do `CLAUDE.md` raiz em
2026-08-09 pelo mesmo motivo dos módulos do backend: é descrição de componente,
não armadilha. **O sistema de design e as regras de layout continuam no raiz.**

- **Dash-planilha** (`frontend/src/rh/DashPlanilha.jsx`): componente RH reutilizável
  — ordena por qualquer coluna, filtra por coluna (texto/select), seleção + ações
  em massa (reusa `CheckMestre`), colunas configuráveis (mostrar/ocultar, salvo em
  `localStorage` por `id` do módulo) e export CSV (BOM UTF-8, abre no Excel-BR) do
  que está filtrado/ordenado. Dirigido por config de colunas
  (`{chave,rotulo,valor,ordenavel,filtro,opcoes,render,sempreVisivel}`). PILOTO no
  Banco de Talentos (`TalentosRH.jsx`). Sort/filtro são EM MEMÓRIA (volumes
  baixos). **ATENÇÃO** (avaliação adversária 2026-07-21): propagar aos outros
  módulos NÃO é plug-and-play. Colaboradores/Admissões filtram SERVER-SIDE
  (recarregam a API a cada filtro) e a base é a folha inteira (LGPD) — trocar
  pelo filtro-em-memória do dash traria tudo ao cliente (regressão de
  performance E de exposição). O componente ainda NÃO tem: cards/métricas no
  topo, nem forma de o pai injetar/controlar filtro (estado interno), nem modo
  server-side, nem paginação. Cards clicáveis→filtro (item 3) exige EVOLUIR o
  dash primeiro (slot de cards + filtro controlável + modo server-side) — piloto
  planejado só no Creche (que já tem `.rh-metrica` e volume baixo). **Coluna de
  texto longo** (cargos, descrição de jornada): marque `quebra: true` na config —
  a célula quebra linha (`white-space: normal`, `max-width: 22rem`) em vez de
  esticar a tabela e forçar rolagem lateral (v1.71). Sem isso, o default é
  `nowrap` (certo para datas/status/botões, ruim para texto livre). **Cards
  clicáveis→filtro** (item 3, v1.72): prop `cards` = `[{rotulo, valor, cor?,
  filtro?:{chave,valor}}]`. Card com `filtro` ativa aquele filtro ao clicar
  (TOGGLE — clicar de novo limpa); o `valor` do filtro é comparado com o
  `textoDe` da coluna, então use o RÓTULO exibido, não o código
  (ex.: 'Novo', não 'novo'). Cards sem `filtro` são indicadores (Total).
  **PADRÃO DE TODAS AS LISTAS do RH** (v1.76/v1.78): Talentos, Jornadas,
  Colaboradores, Admissões e Creche usam o DashPlanilha. Os filtros pesados/
  server-side (posto via SelectBusca, busca com debounce, status do creche)
  ficam FORA do dash, no topo, alimentando `dados`; o dash refina em memória por
  cima. Ao criar uma lista nova, use o DashPlanilha — não escreva `<table>` à mão.
