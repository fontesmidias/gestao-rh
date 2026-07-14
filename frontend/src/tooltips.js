// Dicas por documento — herdadas do PDF "Instruções Importantes para a Admissão".
// Editáveis aqui na v1; na v1.1 passam a ser configuráveis pelo RH sem deploy.
export const DICAS = {
  foto_3x4: {
    nome: 'Foto 3x4 (ou foto digital de rosto)',
    dica: 'Pode ser uma foto tirada agora com o celular: rosto de frente, fundo claro, sem boné e sem óculos escuros.',
  },
  rg: {
    nome: 'RG — frente e verso',
    dica: 'Fotografe a frente e o verso. A CNH NÃO substitui o RG. Se mudou de nome (casamento/divórcio), envie o RG atualizado.',
  },
  cpf_doc: {
    nome: 'CPF',
    dica: 'Pode ser o cartão do CPF ou o comprovante de situação cadastral emitido em receita.fazenda.gov.br.',
  },
  ctps_digital: {
    nome: 'CTPS Digital (PDF)',
    dica: 'Baixe o PDF no app "Carteira de Trabalho Digital" (não envie foto da carteira física azul). No app: Menu → Exportar dados → Gerar PDF.',
  },
  pis_comprovante: {
    nome: 'Comprovante do PIS/PASEP',
    dica: 'Consulte e baixe no app Meu INSS, Caixa Trabalhador ou no próprio app da CTPS Digital.',
  },
  titulo_eleitor_doc: {
    nome: 'Título de Eleitor',
    dica: 'Pode ser foto do título físico ou o e-Título (app). Se não encontrar, emita a certidão em tse.jus.br.',
  },
  reservista: {
    nome: 'Certificado de Reservista',
    dica: 'Obrigatório para homens de 18 a 45 anos. Fotografe frente e verso.',
  },
  habilitacao_prof: {
    nome: 'Habilitação profissional (CNH, CRC, CRM, OAB…)',
    dica: 'Apenas se a sua vaga exigir registro profissional. Se não se aplica, deixe em branco.',
  },
  laudo_pcd: {
    nome: 'Laudo médico (PCD)',
    dica: 'Laudo médico que comprove a deficiência, com CID e assinatura do médico.',
  },
  comp_endereco: {
    nome: 'Comprovante de endereço (últimos 90 dias)',
    dica: 'Conta de luz, água, telefone ou internet dos últimos 90 dias. Pode estar no nome de familiar que mora com você.',
  },
  comp_escolaridade: {
    nome: 'Comprovante de escolaridade',
    dica: 'Certificado ou declaração de conclusão do Ensino Médio (ou histórico escolar).',
  },
  diplomas: {
    nome: 'Diplomas e certificados extras',
    dica: 'Ensino superior, cursos técnicos ou certificações — se tiver, ajudam o seu perfil.',
  },
  nada_consta_eleitoral: {
    nome: 'Certidão de Quitação Eleitoral',
    dica: 'Grátis e na hora no site do TSE: tse.jus.br → Certidões → Quitação eleitoral.',
  },
  nada_consta_criminal: {
    nome: 'Nada Consta Criminal',
    dica: 'Grátis no site do TJDFT (tjdft.jus.br) ou da Polícia Federal (pf.gov.br → antecedentes criminais).',
  },
  cert_casamento: {
    nome: 'Certidão de casamento',
    dica: 'Cópia legível da certidão de casamento ou escritura de união estável.',
  },
  cert_nascimento_dep: {
    nome: 'Certidão de nascimento do dependente',
    dica: 'A certidão precisa mostrar o CPF do dependente (obrigatório para todas as idades).',
  },
  cartao_vacina_dep: {
    nome: 'Cartão de vacina do dependente (0 a 6 anos)',
    dica: 'Fotografe as páginas de identificação e de vacinas aplicadas.',
  },
  declaracao_escolar_dep: {
    nome: 'Declaração escolar do dependente (7 a 14 anos)',
    dica: 'Peça na secretaria da escola uma declaração de matrícula/frequência atualizada.',
  },
  cartao_vt: {
    nome: 'Cartão de Vale-Transporte (DFTrans)',
    dica: 'Foto do cartão mostrando o número (o cartão precisa estar no seu nome).',
  },
}

export const CODIGOS_ERRO_UPLOAD = {
  arquivo_vazio: 'O arquivo veio vazio. Tente selecionar novamente.',
  arquivo_grande_demais: 'O arquivo é muito grande (máx. 50 MB). Tente uma foto com menos resolução.',
  formato_nao_suportado: 'Formato não aceito. Envie foto (JPG/PNG), PDF ou Word.',
  imagem_invalida: 'Não conseguimos abrir essa imagem. Tente tirar a foto de novo.',
  imagem_pequena_demais: 'A imagem ficou muito pequena. Aproxime a câmera e tente de novo.',
  pdf_corrompido: 'Esse PDF parece danificado. Gere o arquivo novamente.',
  conversao_word_falhou: 'Não conseguimos converter esse documento. Tente salvá-lo como PDF.',
  imagem_borrada: 'A foto ficou tremida ou sem foco e não dá para ler. Apoie o celular, aproxime com boa luz e tire de novo.',
  comprovante_antigo: 'Este comprovante tem mais de 90 dias. Envie uma conta recente (luz, água, telefone ou internet) do último mês.',
}
