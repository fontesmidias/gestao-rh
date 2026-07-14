import { useEffect, useRef, useState } from 'react'
import { candidato as api } from '../api.js'
import { Cartao } from './CandidatoApp.jsx'

// Descrições idênticas às do formulário original da Green House.
const GENERO_DESCRICOES = [
  ['cisgenero', 'Cisgênero', 'Pessoa que se identifica com o sexo que lhe foi atribuído no nascimento. (Ex.: alguém que nasceu com o sexo biológico masculino e se identifica como homem).'],
  ['transgenero', 'Transgênero', 'Termo abrangente para quem tem uma identidade de gênero diferente do sexo que lhe foi atribuído no nascimento.'],
  ['transexual', 'Transexual', 'Frequentemente usado como sinônimo de transgênero, mas costuma referir-se a pessoas que buscam ou realizaram alguma transição (social, hormonal ou médica) para alinhar sua aparência física à sua identidade de gênero.'],
  ['travesti', 'Travesti', 'Identidade de gênero feminina, com forte contexto cultural na América Latina. Refere-se a pessoas designadas ao sexo masculino ao nascer, mas que constroem sua identidade e expressão no feminino.'],
  ['genero_fluido', 'Gênero fluido', 'Pessoa cuja identidade de gênero não é fixa. Ela pode transitar entre o masculino, o feminino ou outras identidades ao longo do tempo.'],
  ['agenero', 'Agênero', 'Pessoa que não se identifica com nenhum gênero específico ou que sente a ausência de uma identidade de gênero.'],
  ['nao_informar', 'Prefiro não informar', 'Opção de privacidade para quem escolhe não compartilhar essa informação.'],
]

const OPCOES = {
  sexo: [['feminino', 'Feminino'], ['masculino', 'Masculino']],
  cor_raca: [['branca', 'Branca'], ['preta', 'Preta'], ['parda', 'Parda'],
             ['amarela', 'Amarela'], ['indigena', 'Indígena']],
  nacionalidade: [['brasileira', 'Brasileira'], ['estrangeira', 'Estrangeira']],
  estado_civil: [['solteiro', 'Solteiro(a)'], ['casado', 'Casado(a)'],
                 ['uniao_estavel', 'União estável'], ['divorciado', 'Divorciado(a)'],
                 ['separado', 'Separado(a)'], ['viuvo', 'Viúvo(a)']],
  escolaridade: [['fund_incompleto', 'Fundamental incompleto'], ['fund_completo', 'Fundamental completo'],
                 ['medio_incompleto', 'Médio incompleto'], ['medio_completo', 'Médio completo'],
                 ['sup_incompleto', 'Superior incompleto'], ['sup_completo', 'Superior completo'],
                 ['pos_graduacao', 'Pós-graduação']],
  pix_tipo: [['cpf', 'CPF'], ['celular', 'Celular'], ['email', 'E-mail'], ['aleatoria', 'Chave aleatória']],
  parentesco: [['conjuge', 'Cônjuge/companheiro(a)'], ['filho', 'Filho(a)'], ['menor_guarda', 'Menor sob guarda']],
}

function Campo({ rotulo, dica, ajuda, children }) {
  const [aberta, setAberta] = useState(false)
  return (
    <div className="campo">
      <span className="rotulo">
        {rotulo}{dica && <em className="dica-inline"> — {dica}</em>}
        {ajuda && (
          <button type="button" className="btn-ajuda btn-ajuda-campo" title="Ajuda"
                  onClick={() => setAberta(!aberta)}>?</button>
        )}
      </span>
      {ajuda && aberta && <div className="slot-dica">💡 {ajuda}</div>}
      {children}
    </div>
  )
}

// Mapeia os códigos de pendência da API para linguagem humana + etapa do wizard.
const PENDENCIAS = {
  aceite_lgpd: [0, 'Aceite do aviso de privacidade'],
  'pessoais.data_nascimento': [0, 'Data de nascimento'], 'pessoais.sexo': [0, 'Sexo'],
  'pessoais.identidade_genero': [0, 'Identidade de gênero'], 'pessoais.cor_raca': [0, 'Cor/raça'],
  'pessoais.nacionalidade': [0, 'Nacionalidade'],
  'pessoais.naturalidade_cidade': [0, 'Cidade onde nasceu'], 'pessoais.naturalidade_uf': [0, 'UF onde nasceu'],
  'pessoais.estado_civil': [0, 'Estado civil'], 'pessoais.escolaridade': [0, 'Escolaridade'],
  'pessoais.pcd': [0, 'Pessoa com Deficiência (sim/não)'],
  'endereco.cep': [1, 'CEP'], 'endereco.logradouro_numero_complemento': [1, 'Rua e número'],
  'endereco.bairro': [1, 'Bairro'], 'endereco.cidade': [1, 'Cidade'], 'endereco.uf': [1, 'UF'],
  'documentos.rg_numero': [2, 'Número do RG'], 'documentos.rg_orgao_emissor': [2, 'Órgão emissor do RG'],
  'documentos.rg_data_expedicao': [2, 'Data de expedição do RG'], 'documentos.cpf': [2, 'CPF'],
  'documentos.pis_nis_pasep': [2, 'PIS/NIS/PASEP'],
  'documentos.titulo_eleitor_numero': [2, 'Número do Título de Eleitor'],
  'documentos.titulo_eleitor_zona': [2, 'Zona do Título'], 'documentos.titulo_eleitor_secao': [2, 'Seção do Título'],
  'trabalho_banco.tamanho_calca': [3, 'Tamanho da calça'], 'trabalho_banco.tamanho_camisa': [3, 'Tamanho da camisa'],
  'trabalho_banco.tamanho_calcado': [3, 'Número do calçado'], 'trabalho_banco.banco': [3, 'Banco'],
  'trabalho_banco.pix_tipo': [3, 'Tipo de chave PIX'], 'trabalho_banco.pix_chave': [3, 'Chave PIX'],
  'vt.optante': [5, 'Opção pelo Vale-Transporte (sim/não)'],
  'emergencia.usa_medicamento_continuo': [5, 'Uso contínuo de medicamentos (sim/não)'],
  'emergencia.condicoes_medicas': [5, 'Condições médicas (escreva "Nenhuma" se não tiver)'],
  contatos_emergencia: [5, 'Pelo menos 1 contato de emergência'],
}

function Select({ valor, onChange, opcoes, vazio = 'Selecione…' }) {
  return (
    <select value={valor ?? ''} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">{vazio}</option>
      {opcoes.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
    </select>
  )
}

export default function Wizard({ token, estado, recarregar, aoConcluir }) {
  const [etapa, setEtapa] = useState(0)
  const [dados, setDados] = useState({
    pessoais: { ...estado.pessoais },
    endereco: { ...(estado.endereco || {}) },
    documentos: { ...(estado.documentos || {}) },
    trabalho_banco: { ...(estado.trabalho_banco || {}) },
    dependentes: estado.dependentes || [],
    vt_emergencia: {
      vt_optante: estado.vt?.optante ?? null,
      vt_cartao_dftrans: estado.vt?.cartao_dftrans ?? '',
      vt_trajeto_descricao: estado.vt?.trajeto_descricao ?? '',
      ...(estado.emergencia || {}),
    },
    contatos: estado.contatos_emergencia?.length
      ? estado.contatos_emergencia
      : [{ nome_completo: '', parentesco: '', telefone_celular: '' }],
  })
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(true)
  const [pendencias, setPendencias] = useState(null)
  const primeiraRender = useRef(true)

  // Autosave contínuo: 900ms após a última digitação, a seção atual é gravada.
  useEffect(() => {
    if (primeiraRender.current) { primeiraRender.current = false; return }
    setSalvo(false)
    const timer = setTimeout(async () => {
      try { await salvarEtapa(); setSalvo(true) } catch { /* revalida no avançar */ }
    }, 900)
    return () => clearTimeout(timer)
  }, [dados])

  const setSec = (sec, campo, valor) =>
    setDados((d) => ({ ...d, [sec]: { ...d[sec], [campo]: valor } }))

  const salvarEtapa = async () => {
    setSalvando(true)
    try {
      if (etapa === 0) await api.salvarSecao(token, 'pessoais', dados.pessoais)
      if (etapa === 1) await api.salvarSecao(token, 'endereco', dados.endereco)
      if (etapa === 2) await api.salvarSecao(token, 'documentos', dados.documentos)
      if (etapa === 3) await api.salvarSecao(token, 'trabalho-banco', dados.trabalho_banco)
      if (etapa === 4) await api.salvarSecao(token, 'dependentes',
        dados.dependentes.filter((d) => d.nome_completo))
      if (etapa === 5) {
        const { vt_optante, vt_cartao_dftrans, vt_trajeto_descricao, ...emergencia } = dados.vt_emergencia
        await api.salvarSecao(token, 'vt-emergencia',
          { vt_optante, vt_cartao_dftrans, vt_trajeto_descricao, ...emergencia })
        await api.salvarSecao(token, 'contatos-emergencia',
          dados.contatos.filter((c) => c.nome_completo))
      }
    } finally { setSalvando(false) }
  }

  const proxima = async () => {
    await salvarEtapa()
    if (etapa < 5) { setEtapa(etapa + 1); window.scrollTo(0, 0); return }
    try {
      await api.declarar(token)
      await recarregar()
      aoConcluir()
    } catch (e) {
      if (e.status === 422) setPendencias(e.detail.pendencias)
    }
  }

  const voltar = async () => { await salvarEtapa(); setEtapa(Math.max(0, etapa - 1)) }

  const p = dados.pessoais, en = dados.endereco, doc = dados.documentos
  const tb = dados.trabalho_banco, ve = dados.vt_emergencia

  const busca_cep = async () => {
    const cep = (en.cep || '').replace(/\D/g, '')
    if (cep.length !== 8) return
    try {
      const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`).then((x) => x.json())
      if (!r.erro) setDados((d) => ({ ...d, endereco: {
        ...d.endereco, cep,
        logradouro_numero_complemento: d.endereco.logradouro_numero_complemento || r.logradouro,
        bairro: r.bairro || d.endereco.bairro,
        cidade: r.localidade || d.endereco.cidade,
        uf: r.uf || d.endereco.uf,
      } }))
    } catch { /* offline: segue manual */ }
  }

  const TITULOS = ['Sobre você', 'Seu endereço', 'Seus documentos', 'Trabalho e banco',
                   'Dependentes', 'Vale-transporte e emergência']

  return (
    <Cartao>
      <div className="progresso">
        <div className="progresso-barra" style={{ width: `${((etapa + 1) / 6) * 100}%` }} />
      </div>
      <p className="etapa-num">Parte 1 de 4 — Seus dados · passo {etapa + 1} de 6 ·{' '}
        {salvo ? 'salvo ✓' : 'salvando…'}</p>
      <h2>{TITULOS[etapa]}</h2>
      {etapa === 5 && (
        <p className="explica">Este é o último passo dos seus dados. Ao confirmar,
          você seguirá para a <strong>assinatura dos 3 documentos</strong> (parte 2 de 4).</p>
      )}

      {etapa === 0 && <>
        <Campo rotulo="Nome completo"><input value={p.nome_completo || ''}
          onChange={(e) => setSec('pessoais', 'nome_completo', e.target.value)} /></Campo>
        <Campo rotulo="Data de nascimento"><input type="date" value={p.data_nascimento || ''}
          onChange={(e) => setSec('pessoais', 'data_nascimento', e.target.value)} /></Campo>
        <Campo rotulo="Sexo (conforme registro civil)">
          <Select valor={p.sexo} opcoes={OPCOES.sexo}
                  onChange={(v) => setSec('pessoais', 'sexo', v)} /></Campo>
        <div className="campo">
          <span className="rotulo">Identidade de gênero</span>
          <div className="radios">
            {GENERO_DESCRICOES.map(([v, nome, descricao]) => (
              <label className={`radio-desc ${p.identidade_genero === v ? 'marcado' : ''}`} key={v}>
                <input type="radio" name="identidade_genero" checked={p.identidade_genero === v}
                       onChange={() => setSec('pessoais', 'identidade_genero', v)} />
                <span><strong>{nome}:</strong> {descricao}</span>
              </label>
            ))}
          </div>
        </div>
        <Campo rotulo="Cor/raça (autodeclaração, IBGE)">
          <Select valor={p.cor_raca} opcoes={OPCOES.cor_raca}
                  onChange={(v) => setSec('pessoais', 'cor_raca', v)} /></Campo>
        <Campo rotulo="Nacionalidade">
          <Select valor={p.nacionalidade} opcoes={OPCOES.nacionalidade}
                  onChange={(v) => setSec('pessoais', 'nacionalidade', v)} /></Campo>
        <div className="linha2">
          <Campo rotulo="Cidade onde nasceu"><input value={p.naturalidade_cidade || ''}
            onChange={(e) => setSec('pessoais', 'naturalidade_cidade', e.target.value)} /></Campo>
          <Campo rotulo="UF"><input maxLength={2} value={p.naturalidade_uf || ''}
            onChange={(e) => setSec('pessoais', 'naturalidade_uf', e.target.value.toUpperCase())} /></Campo>
        </div>
        <Campo rotulo="Estado civil">
          <Select valor={p.estado_civil} opcoes={OPCOES.estado_civil}
                  onChange={(v) => setSec('pessoais', 'estado_civil', v)} /></Campo>
        <Campo rotulo="Escolaridade">
          <Select valor={p.escolaridade} opcoes={OPCOES.escolaridade}
                  onChange={(v) => setSec('pessoais', 'escolaridade', v)} /></Campo>
        <Campo rotulo="Você é Pessoa com Deficiência (PCD)?">
          <Select valor={p.pcd == null ? null : String(p.pcd)}
                  opcoes={[['true', 'Sim'], ['false', 'Não']]}
                  onChange={(v) => setSec('pessoais', 'pcd', v == null ? null : v === 'true')} /></Campo>
        <Campo rotulo="E-mail"><input type="email" value={p.email || ''}
          onChange={(e) => setSec('pessoais', 'email', e.target.value)} /></Campo>
        <Campo rotulo="Celular / WhatsApp (com DDD)">
          <input placeholder="(61) 99999-8888" inputMode="tel" value={p.celular_whatsapp || ''}
                 onChange={(e) => setSec('pessoais', 'celular_whatsapp',
                                          e.target.value.replace(/[^\d() -]/g, ''))} /></Campo>
      </>}

      {etapa === 1 && <>
        <Campo rotulo="CEP" dica="informe o CEP exato da sua quadra/rua">
          <input value={en.cep || ''} onBlur={busca_cep} inputMode="numeric" maxLength={9}
                 onChange={(e) => setSec('endereco', 'cep', e.target.value.replace(/\D/g, ''))} /></Campo>
        <Campo rotulo="Rua, número e complemento"><input
          value={en.logradouro_numero_complemento || ''}
          onChange={(e) => setSec('endereco', 'logradouro_numero_complemento', e.target.value)} /></Campo>
        <Campo rotulo="Bairro"><input value={en.bairro || ''}
          onChange={(e) => setSec('endereco', 'bairro', e.target.value)} /></Campo>
        <div className="linha2">
          <Campo rotulo="Cidade"><input value={en.cidade || ''}
            onChange={(e) => setSec('endereco', 'cidade', e.target.value)} /></Campo>
          <Campo rotulo="UF"><input maxLength={2} value={en.uf || ''}
            onChange={(e) => setSec('endereco', 'uf', e.target.value.toUpperCase())} /></Campo>
        </div>
      </>}

      {etapa === 2 && <>
        <Campo rotulo="RG — número" dica="a CNH não substitui o RG">
          <input value={doc.rg_numero || ''}
                 onChange={(e) => setSec('documentos', 'rg_numero', e.target.value)} /></Campo>
        <div className="linha2">
          <Campo rotulo="Órgão emissor" dica="ex.: SSP/DF"><input value={doc.rg_orgao_emissor || ''}
            onChange={(e) => setSec('documentos', 'rg_orgao_emissor', e.target.value)} /></Campo>
          <Campo rotulo="Data de expedição"><input type="date" value={doc.rg_data_expedicao || ''}
            onChange={(e) => setSec('documentos', 'rg_data_expedicao', e.target.value)} /></Campo>
        </div>
        <Campo rotulo="CPF"><input inputMode="numeric" maxLength={14} value={doc.cpf || ''}
          onChange={(e) => setSec('documentos', 'cpf', e.target.value.replace(/\D/g, ''))} /></Campo>
        <Campo rotulo="PIS / NIS / PASEP"
               ajuda="Não sabe o número? Abra o app 'Carteira de Trabalho Digital', 'Meu INSS' ou 'Caixa Trabalhador' — o número aparece na tela inicial ou no seu perfil. São 11 números.">
          <input inputMode="numeric" value={doc.pis_nis_pasep || ''}
                 onChange={(e) => setSec('documentos', 'pis_nis_pasep', e.target.value.replace(/\D/g, ''))} /></Campo>
        <div className="linha2">
          <Campo rotulo="CNH — número (se tiver)"><input value={doc.cnh_numero || ''}
            onChange={(e) => setSec('documentos', 'cnh_numero', e.target.value)} /></Campo>
          <Campo rotulo="CNH — categoria"><input value={doc.cnh_categoria || ''}
            onChange={(e) => setSec('documentos', 'cnh_categoria', e.target.value.toUpperCase())} /></Campo>
        </div>
        <Campo rotulo="Título de Eleitor — número"
               ajuda="O número, a zona e a seção aparecem no título físico ou no app e-Título. Não tem o título em mãos? Consulte grátis em tse.jus.br → Autoatendimento → Título de eleitor.">
          <input inputMode="numeric"
          value={doc.titulo_eleitor_numero || ''}
          onChange={(e) => setSec('documentos', 'titulo_eleitor_numero', e.target.value.replace(/\D/g, ''))} /></Campo>
        <div className="linha2">
          <Campo rotulo="Zona"><input inputMode="numeric" value={doc.titulo_eleitor_zona || ''}
            onChange={(e) => setSec('documentos', 'titulo_eleitor_zona', e.target.value.replace(/\D/g, ''))} /></Campo>
          <Campo rotulo="Seção"><input inputMode="numeric" value={doc.titulo_eleitor_secao || ''}
            onChange={(e) => setSec('documentos', 'titulo_eleitor_secao', e.target.value.replace(/\D/g, ''))} /></Campo>
        </div>
      </>}

      {etapa === 3 && <>
        <div className="linha2">
          <Campo rotulo="Calça"><input value={tb.tamanho_calca || ''}
            onChange={(e) => setSec('trabalho_banco', 'tamanho_calca', e.target.value)} /></Campo>
          <Campo rotulo="Camisa"><input value={tb.tamanho_camisa || ''}
            onChange={(e) => setSec('trabalho_banco', 'tamanho_camisa', e.target.value)} /></Campo>
        </div>
        <Campo rotulo="Calçado"><input value={tb.tamanho_calcado || ''}
          onChange={(e) => setSec('trabalho_banco', 'tamanho_calcado', e.target.value)} /></Campo>
        <Campo rotulo="Banco" dica="onde você recebe (ex.: BRB, Caixa, Nubank)">
          <input value={tb.banco || ''}
                 onChange={(e) => setSec('trabalho_banco', 'banco', e.target.value)} /></Campo>
        <Campo rotulo="Tipo de chave PIX">
          <Select valor={tb.pix_tipo} opcoes={OPCOES.pix_tipo}
                  onChange={(v) => setSec('trabalho_banco', 'pix_tipo', v)} /></Campo>
        <Campo rotulo="Chave PIX"><input value={tb.pix_chave || ''}
          onChange={(e) => setSec('trabalho_banco', 'pix_chave', e.target.value)} /></Campo>
      </>}

      {etapa === 4 && <>
        <p className="explica">Dependentes: cônjuge/companheiro(a), filhos até 21 anos (24 se no
          ensino superior) ou menor sob sua guarda judicial. <strong>CPF é obrigatório para
          todos, inclusive recém-nascidos.</strong> Se não tiver, toque em "Continuar".</p>
        {dados.dependentes.map((dep, i) => (
          <fieldset className="dependente" key={i}>
            <legend>Dependente {i + 1}</legend>
            <Campo rotulo="Nome completo"><input value={dep.nome_completo || ''}
              onChange={(e) => atualizaDep(i, 'nome_completo', e.target.value)} /></Campo>
            <div className="linha2">
              <Campo rotulo="Nascimento"><input type="date" value={dep.data_nascimento || ''}
                onChange={(e) => atualizaDep(i, 'data_nascimento', e.target.value)} /></Campo>
              <Campo rotulo="CPF"><input inputMode="numeric" value={dep.cpf || ''}
                onChange={(e) => atualizaDep(i, 'cpf', e.target.value.replace(/\D/g, ''))} /></Campo>
            </div>
            <Campo rotulo="Parentesco">
              <Select valor={dep.parentesco} opcoes={OPCOES.parentesco}
                      onChange={(v) => atualizaDep(i, 'parentesco', v)} /></Campo>
            <Campo rotulo="Incluir na dedução do Imposto de Renda (IRRF)?">
              <Select valor={dep.deduz_irrf == null ? null : String(dep.deduz_irrf)}
                      opcoes={[['true', 'Sim'], ['false', 'Não']]}
                      onChange={(v) => atualizaDep(i, 'deduz_irrf', v === 'true')} /></Campo>
            <button className="btn-remover" onClick={() =>
              setDados((d) => ({ ...d, dependentes: d.dependentes.filter((_, j) => j !== i) }))}>
              Remover</button>
          </fieldset>
        ))}
        <button className="btn-secundario" onClick={() => setDados((d) => ({
          ...d, dependentes: [...d.dependentes,
            { nome_completo: '', data_nascimento: '', cpf: '', parentesco: null, deduz_irrf: false }],
        }))}>+ Adicionar dependente</button>
      </>}

      {etapa === 5 && <>
        <Campo rotulo="Você quer receber o Vale-Transporte (VT)?"
               dica="se optar, a empresa desconta até 6% do salário básico (nunca mais do que o transporte custa)">
          <Select valor={ve.vt_optante == null ? null : String(ve.vt_optante)}
                  opcoes={[['true', 'Sim — quero receber o VT'], ['false', 'Não — não quero o VT']]}
                  onChange={(v) => setSec('vt_emergencia', 'vt_optante', v == null ? null : v === 'true')} /></Campo>
        {ve.vt_optante && <>
          <Campo rotulo="Número do cartão DFTrans (se já tiver)"
                 dica="ainda não tem? Deixe em branco e providenciamos com você">
            <input value={ve.vt_cartao_dftrans || ''}
                   onChange={(e) => setSec('vt_emergencia', 'vt_cartao_dftrans', e.target.value)} /></Campo>
          <Campo rotulo="Trajeto casa ↔ trabalho"
                 dica="linhas de ônibus/metrô da ida e da volta e o valor, se souber">
            <textarea rows={2} value={ve.vt_trajeto_descricao || ''}
                      onChange={(e) => setSec('vt_emergencia', 'vt_trajeto_descricao', e.target.value)} /></Campo>
        </>}
        <hr />
        <h3>Para emergências</h3>
        <Campo rotulo="Tipo sanguíneo (se souber)"><input placeholder="ex.: O+"
          value={ve.tipo_sanguineo || ''}
          onChange={(e) => setSec('vt_emergencia', 'tipo_sanguineo', e.target.value)} /></Campo>
        <Campo rotulo="Faz uso contínuo de medicamentos?">
          <Select valor={ve.usa_medicamento_continuo == null ? null : String(ve.usa_medicamento_continuo)}
                  opcoes={[['true', 'Sim'], ['false', 'Não']]}
                  onChange={(v) => setSec('vt_emergencia', 'usa_medicamento_continuo', v == null ? null : v === 'true')} /></Campo>
        {ve.usa_medicamento_continuo && (
          <Campo rotulo="Quais medicamentos?"><input value={ve.medicamentos || ''}
            onChange={(e) => setSec('vt_emergencia', 'medicamentos', e.target.value)} /></Campo>)}
        <Campo rotulo="Alguma condição médica importante?"
               dica="alergias, diabetes, hipertensão… Se não tiver, escreva 'Nenhuma'">
          <input value={ve.condicoes_medicas || ''}
                 onChange={(e) => setSec('vt_emergencia', 'condicoes_medicas', e.target.value)} /></Campo>
        <Campo rotulo="Alguma orientação específica em caso de emergência? (opcional)">
          <input value={ve.orientacao_emergencia || ''}
                 onChange={(e) => setSec('vt_emergencia', 'orientacao_emergencia', e.target.value)} /></Campo>
        <h3>Contatos de emergência</h3>
        {dados.contatos.map((c, i) => (
          <fieldset className="dependente" key={i}>
            <legend>Contato {i + 1}</legend>
            <Campo rotulo="Nome completo"><input value={c.nome_completo || ''}
              onChange={(e) => atualizaContato(i, 'nome_completo', e.target.value)} /></Campo>
            <div className="linha2">
              <Campo rotulo="Parentesco"><input value={c.parentesco || ''}
                onChange={(e) => atualizaContato(i, 'parentesco', e.target.value)} /></Campo>
              <Campo rotulo="Celular (com DDD)">
                <input placeholder="(61) 99999-8888" inputMode="tel" value={c.telefone_celular || ''}
                       onChange={(e) => atualizaContato(i, 'telefone_celular',
                                                        e.target.value.replace(/[^\d() -]/g, ''))} /></Campo>
            </div>
          </fieldset>
        ))}
        <button className="btn-secundario" onClick={() => setDados((d) => ({
          ...d, contatos: [...d.contatos, { nome_completo: '', parentesco: '', telefone_celular: '' }],
        }))}>+ Adicionar contato</button>
      </>}

      {pendencias && (
        <div className="alerta">
          <strong>Ainda falta preencher:</strong>
          <ul className="lista-pendencias">
            {pendencias.map((cod) => {
              const [etapaAlvo, rotulo] = PENDENCIAS[cod] || [null, cod]
              return (
                <li key={cod}>
                  {rotulo}
                  {etapaAlvo != null && (
                    <button className="btn-link" onClick={() => {
                      setPendencias(null); setEtapa(etapaAlvo); window.scrollTo(0, 0)
                    }}>ir para a etapa {etapaAlvo + 1} →</button>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}

      <div className="navegacao">
        {etapa > 0 && <button className="btn-secundario" onClick={voltar}>← Voltar</button>}
        <button className="btn-principal" disabled={salvando} onClick={proxima}>
          {salvando ? 'Salvando…' : etapa < 5 ? 'Continuar →' : 'Confirmar e declarar veracidade'}
        </button>
      </div>
    </Cartao>
  )

  function atualizaDep(i, campo, valor) {
    setDados((d) => ({
      ...d,
      dependentes: d.dependentes.map((dep, j) => (j === i ? { ...dep, [campo]: valor } : dep)),
    }))
  }
  function atualizaContato(i, campo, valor) {
    setDados((d) => ({
      ...d,
      contatos: d.contatos.map((c, j) => (j === i ? { ...c, [campo]: valor } : c)),
    }))
  }
}
