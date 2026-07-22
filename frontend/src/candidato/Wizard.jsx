import { useEffect, useRef, useState } from 'react'
import { candidato as api } from '../api.js'
import { Cartao } from './CandidatoApp.jsx'
import { CODIGOS_ERRO_UPLOAD, NOMES_SUGESTAO, SECAO_SUGESTAO } from '../tooltips.js'
import { fmtCpf, cpfValido, fmtTelefone } from '../fmt.js'
import Espera from '../Espera.jsx'
import CapturaDocumento from './Camera.jsx'

// cpfValido é reexportado por compatibilidade (Entrar.jsx importava daqui).
export { cpfValido }

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

// Dígitos verificadores do CPF (algoritmo oficial da Receita).
function AvisoCpf({ cpf }) {
  const n = (cpf || '').replace(/\D/g, '')
  if (n.length !== 11 || cpfValido(n)) return null
  return <div className="alerta" style={{ marginTop: '.35rem', padding: '.5rem .75rem' }}>
    Este CPF não existe — confira os números digitados.</div>
}

// Campo de data digitada com máscara dd/mm/aaaa: muito mais fácil para quem não
// domina o seletor de calendário do celular. Guarda ISO (aaaa-mm-dd) por baixo.
function InputData({ valor, onChange }) {
  const isoParaBr = (iso) => {
    if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso || ''
    const [a, m, d] = iso.split('-')
    return `${d}/${m}/${a}`
  }
  const [texto, setTexto] = useState(isoParaBr(valor))
  const [erro, setErro] = useState(null)

  const aoDigitar = (e) => {
    const n = e.target.value.replace(/\D/g, '').slice(0, 8)
    let fmt = n
    if (n.length > 4) fmt = `${n.slice(0, 2)}/${n.slice(2, 4)}/${n.slice(4)}`
    else if (n.length > 2) fmt = `${n.slice(0, 2)}/${n.slice(2)}`
    setTexto(fmt)
    setErro(null)
    if (n.length === 8) {
      const d = Number(n.slice(0, 2)), m = Number(n.slice(2, 4)), a = Number(n.slice(4))
      const data = new Date(a, m - 1, d)
      const valida = data.getFullYear() === a && data.getMonth() === m - 1 && data.getDate() === d
      if (!valida || a < 1900 || a > new Date().getFullYear() + 1) {
        setErro('Essa data não existe — confira o dia, o mês e o ano.')
        return
      }
      onChange(`${n.slice(4)}-${n.slice(2, 4)}-${n.slice(0, 2)}`)
    } else if (valor) {
      onChange(null)
    }
  }
  return (
    <>
      <input inputMode="numeric" placeholder="dd/mm/aaaa" maxLength={10}
             value={texto} onChange={aoDigitar} />
      {erro && <div className="alerta" style={{ marginTop: '.35rem', padding: '.5rem .75rem' }}>{erro}</div>}
    </>
  )
}

// Foto do RG OU da CNH → OCR sugere o preenchimento. É uma escolha, não uma
// obrigação: quem preferir digita tudo normalmente. A foto já vale como envio
// do documento no checklist (mata duas etapas de uma vez).
function LeitorRG({ token, dados, setDados, salvar }) {
  const [camera, setCamera] = useState(false)
  const [lendo, setLendo] = useState(false)
  const [resultado, setResultado] = useState(null) // {aplicados, cnh} | {vazio, cnh}
  const [erro, setErro] = useState(null)

  const processar = async (arquivo) => {
    setCamera(false)
    if (!arquivo) return
    setErro(null); setResultado(null); setLendo(true)
    try {
      // O backend detecta se é RG ou CNH e guarda no slot certo do checklist.
      const r = await api.enviarIdentidade(token, arquivo)
      const sug = r.sugestoes || {}
      const cnh = r.documento_detectado === 'cnh'
      const aplicados = []
      const novos = JSON.parse(JSON.stringify(dados))
      for (const [campo, valor] of Object.entries(sug)) {
        const sec = SECAO_SUGESTAO[campo]
        if (sec && !novos[sec][campo]) {   // nunca sobrescreve o que já foi digitado
          novos[sec][campo] = valor
          aplicados.push(NOMES_SUGESTAO[campo] || campo)
        }
      }
      if (aplicados.length) {
        setDados(novos)
        await salvar(novos)
      }
      setResultado(aplicados.length ? { aplicados, cnh } : { vazio: true, cnh })
    } catch (err) {
      setErro(CODIGOS_ERRO_UPLOAD?.[err.detail]
        || 'Não conseguimos ler a foto. Você pode preencher normalmente abaixo.')
    } finally { setLendo(false) }
  }

  return (
    <div className="leitor-rg">
      {camera && (
        <CapturaDocumento formato="cartao" titulo="Fotografar RG ou CNH"
                          passos={[{ rotulo: 'FRENTE' },
                                   { rotulo: 'VERSO', opcional: true }]}
                          aoCapturar={processar} aoArquivo={processar}
                          aoFechar={() => setCamera(false)} />
      )}
      <button type="button" className="btn-secundario" disabled={lendo}
              onClick={() => setCamera(true)}>
        📷 {lendo ? 'Lendo o seu documento…' : 'Fotografar meu RG ou CNH e preencher automaticamente'}
      </button>
      <p className="explica" style={{ margin: '.4rem 0 0' }}>Você escolhe: mande a foto e
        nós sugerimos o preenchimento (ela já vale como envio do documento na etapa 3),
        ou simplesmente digite os campos abaixo — dá tudo certo dos dois jeitos.</p>
      {lendo && <Espera texto="Lendo o documento e preparando as sugestões…" />}
      {erro && <div className="alerta">{erro}</div>}
      {resultado?.vazio && (
        <div className="alerta">Recebemos a foto (o documento já conta como enviado ✓),
          mas não conseguimos ler os dados com segurança. Preencha os campos normalmente.</div>
      )}
      {resultado?.aplicados && (
        <div className="sucesso">
          <strong>Preenchemos automaticamente:</strong> {resultado.aplicados.join(', ')}.
          <br /><strong>Confira cada um antes de continuar</strong> — a leitura é uma ajuda,
          mas a responsabilidade pelas informações enviadas é sua. Corrija o que for preciso.
          <br /><small>Sua foto também já ficou registrada como enviada ✓.</small>
        </div>
      )}
      {resultado?.cnh && (
        <div className="alerta">Percebemos que a foto é de uma <strong>CNH</strong> —
          registramos como habilitação. Para a admissão o RG também é necessário:
          envie a foto dele na etapa de documentos, quando puder.</div>
      )}
    </div>
  )
}

// Foto do cabeçalho da conta (luz, água, internet…) na etapa de endereço:
// a foto já vale como envio do comprovante no checklist, e o CEP lido
// dispara a mesma busca de endereço da digitação manual.
function LeitorComprovante({ token, aoCep }) {
  const [camera, setCamera] = useState(false)
  const [lendo, setLendo] = useState(false)
  const [resultado, setResultado] = useState(null) // 'cep' | 'so-envio'
  const [erro, setErro] = useState(null)

  const processar = async (arquivo) => {
    setCamera(false)
    if (!arquivo) return
    setErro(null); setResultado(null); setLendo(true)
    try {
      const check = await api.documentos(token)
      const slot = check.slots.find((s) => s.tipo === 'comp_endereco')
      if (!slot) throw new Error('sem_slot')
      const r = await api.enviarArquivo(token, slot.id, arquivo)
      const cep = r.sugestoes?.cep
      if (cep) await aoCep(cep)
      setResultado(cep ? 'cep' : 'so-envio')
    } catch (err) {
      setErro(CODIGOS_ERRO_UPLOAD?.[err.detail]
        || 'Não conseguimos ler a foto. Você pode preencher normalmente abaixo.')
    } finally { setLendo(false) }
  }

  return (
    <div className="leitor-rg">
      {camera && (
        <CapturaDocumento formato="cabecalho" titulo="Fotografar comprovante de endereço"
                          aoCapturar={processar} aoArquivo={processar}
                          aoFechar={() => setCamera(false)} />
      )}
      <button type="button" className="btn-secundario" disabled={lendo}
              onClick={() => setCamera(true)}>
        📷 {lendo ? 'Lendo o comprovante…' : 'Fotografar minha conta (luz, água…) e preencher o endereço'}
      </button>
      <p className="explica" style={{ margin: '.4rem 0 0' }}>Aponte para o <strong>cabeçalho</strong> da
        conta — a parte de cima, onde aparecem o nome e o endereço. A foto já vale como envio do
        comprovante na etapa de documentos. Prefere digitar? Siga nos campos abaixo.</p>
      {lendo && <Espera texto="Lendo o comprovante…" />}
      {erro && <div className="alerta">{erro}</div>}
      {resultado === 'cep' && (
        <div className="sucesso">
          <strong>Encontramos o CEP e preenchemos o endereço.</strong> Confira rua, número e
          complemento — a responsabilidade pelas informações é sua. Ajuste o que for preciso.
          <br /><small>Seu comprovante também já ficou registrado como enviado ✓.</small>
        </div>
      )}
      {resultado === 'so-envio' && (
        <div className="alerta">Recebemos a foto (o comprovante já conta como enviado ✓), mas não
          conseguimos ler o CEP com segurança. Preencha os campos normalmente.</div>
      )}
    </div>
  )
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
  'pessoais.email': [0, 'E-mail (o código de assinatura chega por ele)'],
  'pessoais.data_nascimento': [0, 'Data de nascimento'], 'pessoais.sexo': [0, 'Sexo'],
  'pessoais.identidade_genero': [0, 'Identidade de gênero'], 'pessoais.cor_raca': [0, 'Cor/raça'],
  'pessoais.nacionalidade': [0, 'Nacionalidade'],
  'pessoais.naturalidade_cidade': [0, 'Cidade onde nasceu'], 'pessoais.naturalidade_uf': [0, 'UF onde nasceu'],
  'pessoais.estado_civil': [0, 'Estado civil'], 'pessoais.escolaridade': [0, 'Escolaridade'],
  'pessoais.pcd': [0, 'Pessoa com Deficiência (sim/não)'],
  'endereco.cep': [1, 'CEP'], 'endereco.logradouro_numero_complemento': [1, 'Rua e número'],
  'endereco.logradouro': [1, 'Logradouro (rua/quadra)'], 'endereco.numero': [1, 'Número'],
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
      vt_ciencia_cartao_go: Boolean(estado.vt?.ciencia_cartao_go_em),
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

  const [erroSalvar, setErroSalvar] = useState(null)

  // Autosave contínuo: 900ms após a última digitação, a seção atual é gravada.
  useEffect(() => {
    if (primeiraRender.current) { primeiraRender.current = false; return }
    setSalvo(false)
    const timer = setTimeout(async () => {
      try {
        await salvarEtapa()
        setSalvo(true)
        setErroSalvar(null)
      } catch (e) {
        // Erro NUNCA fica mudo: mostra o campo e o motivo.
        let detalhe = 'verifique sua conexão.'
        if (Array.isArray(e.detail)) {
          detalhe = e.detail
            .map((d) => `${(PENDENCIAS[`x.${d.loc?.slice(-1)[0]}`] || [null, d.loc?.slice(-1)[0]])[1]}: ${d.msg}`)
            .join('; ')
        } else if (typeof e.detail === 'string') detalhe = e.detail
        setErroSalvar(`Não foi possível salvar automaticamente — ${detalhe}`)
      }
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
        const { vt_optante, vt_cartao_dftrans, vt_trajeto_descricao,
                vt_ciencia_cartao_go, ...emergencia } = dados.vt_emergencia
        await api.salvarSecao(token, 'vt-emergencia',
          { vt_optante, vt_cartao_dftrans, vt_trajeto_descricao,
            vt_ciencia_cartao_go, ...emergencia })
        await api.salvarSecao(token, 'contatos-emergencia',
          dados.contatos.filter((c) => c.nome_completo))
      }
    } finally { setSalvando(false) }
  }

  const proxima = async () => {
    try {
      await salvarEtapa()
      setErroSalvar(null)
    } catch (e) {
      setErroSalvar('Alguns campos não puderam ser salvos — confira os valores digitados '
        + (Array.isArray(e.detail)
           ? `(${e.detail.map((d) => d.loc?.slice(-1)[0]).join(', ')})` : '')
        + ' e tente novamente.')
      return
    }
    if (etapa < 5) { setEtapa(etapa + 1); window.scrollTo(0, 0); return }
    try {
      await api.declarar(token)
      await recarregar()
      aoConcluir()
    } catch (e) {
      if (e.status === 422) setPendencias(e.detail.pendencias)
      else setErroSalvar('Não foi possível concluir. Verifique sua conexão e tente novamente.')
    }
  }

  const voltar = async () => { await salvarEtapa(); setEtapa(Math.max(0, etapa - 1)) }

  const p = dados.pessoais, en = dados.endereco, doc = dados.documentos
  const tb = dados.trabalho_banco, ve = dados.vt_emergencia

  const buscaCepValor = async (valor) => {
    const cep = (valor || '').replace(/\D/g, '')
    if (cep.length !== 8) return
    try {
      const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`).then((x) => x.json())
      if (!r.erro) setDados((d) => ({ ...d, endereco: {
        ...d.endereco, cep,
        logradouro: d.endereco.logradouro || r.logradouro,
        bairro: r.bairro || d.endereco.bairro,
        cidade: r.localidade || d.endereco.cidade,
        uf: r.uf || d.endereco.uf,
      } }))
    } catch { /* offline: segue manual */ }
  }
  const busca_cep = () => buscaCepValor(en.cep)

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
        <LeitorRG token={token} dados={dados} setDados={setDados} salvar={async (novos) => {
          await api.salvarSecao(token, 'pessoais', novos.pessoais)
          await api.salvarSecao(token, 'documentos', novos.documentos)
        }} />
        <Campo rotulo="Nome completo"><input value={p.nome_completo || ''}
          onChange={(e) => setSec('pessoais', 'nome_completo', e.target.value)} /></Campo>
        <Campo rotulo="Nome social (se tiver)"
               ajuda="Preencha apenas se você deseja ser chamado(a) por um nome diferente do que está no seu registro civil (Decreto 8.727/2016). Ele aparecerá nos seus documentos junto ao nome civil. Se não for o seu caso, deixe em branco.">
          <input value={p.nome_social || ''}
                 onChange={(e) => setSec('pessoais', 'nome_social', e.target.value)} /></Campo>
        <Campo rotulo="Nome completo da sua mãe"
               ajuda="Como está nos seus documentos (certidão de nascimento ou RG).">
          <input value={p.nome_mae || ''}
                 onChange={(e) => setSec('pessoais', 'nome_mae', e.target.value)} /></Campo>
        <Campo rotulo="Nome completo do seu pai"
               ajuda="Se o pai não consta nos seus documentos (não declarado), deixe este campo em branco — sem problema algum.">
          <input value={p.nome_pai || ''}
                 onChange={(e) => setSec('pessoais', 'nome_pai', e.target.value)} /></Campo>
        <Campo rotulo="Data de nascimento" dica="só números: dia, mês e ano"><InputData valor={p.data_nascimento || ''}
          onChange={(v) => setSec('pessoais', 'data_nascimento', v)} /></Campo>
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
        {p.pcd === true && <>
          {/* dados do laudo médico (Lei 8.213/91) — opcionais; o laudo anexado
              é a prova, estes campos poupam transcrição do RH */}
          <Campo rotulo="Tipo de deficiência (conforme o laudo)">
            <Select valor={p.pcd_tipo}
                    opcoes={[['fisica', 'Física'], ['visual', 'Visual'],
                             ['auditiva', 'Auditiva'], ['intelectual', 'Intelectual'],
                             ['multipla', 'Múltipla']]}
                    onChange={(v) => setSec('pessoais', 'pcd_tipo', v)} /></Campo>
          <div className="linha2">
            <Campo rotulo="CID (do laudo)"><input value={p.pcd_cid || ''}
              onChange={(e) => setSec('pessoais', 'pcd_cid', e.target.value.toUpperCase())} /></Campo>
            <Campo rotulo="Data do laudo"><input type="date" value={p.pcd_data_laudo || ''}
              onChange={(e) => setSec('pessoais', 'pcd_data_laudo', e.target.value || null)} /></Campo>
          </div>
          <Campo rotulo="Médico e CRM (do laudo)">
            <input placeholder="Dr(a). Nome — CRM/DF 12345" value={p.pcd_medico_crm || ''}
              onChange={(e) => setSec('pessoais', 'pcd_medico_crm', e.target.value)} /></Campo>
        </>}
        <Campo rotulo="E-mail"><input type="email" value={p.email || ''}
          onChange={(e) => setSec('pessoais', 'email', e.target.value)} /></Campo>
        <Campo rotulo="Celular / WhatsApp (com DDD)">
          <input placeholder="(61) 99999-8888" inputMode="tel" value={fmtTelefone(p.celular_whatsapp)}
                 onChange={(e) => setSec('pessoais', 'celular_whatsapp',
                                          fmtTelefone(e.target.value))} /></Campo>
      </>}

      {etapa === 1 && <>
        <LeitorComprovante token={token} aoCep={buscaCepValor} />
        <Campo rotulo="CEP" dica="informe o CEP exato da sua quadra/rua">
          <input value={en.cep || ''} onBlur={busca_cep} inputMode="numeric" maxLength={9}
                 onChange={(e) => setSec('endereco', 'cep', e.target.value.replace(/\D/g, ''))} /></Campo>
        {en.logradouro_numero_complemento && !en.logradouro ? (
          /* quem começou a ficha antes desta versão segue no campo único —
             não obrigamos a redigitar o endereço no meio do caminho */
          <Campo rotulo="Rua, número e complemento"><input
            value={en.logradouro_numero_complemento || ''}
            onChange={(e) => setSec('endereco', 'logradouro_numero_complemento', e.target.value)} /></Campo>
        ) : (<>
          <Campo rotulo="Logradouro (rua / quadra / conjunto)"
                 dica="ex.: QN 7 Conjunto 5, ou Rua das Palmeiras">
            <input value={en.logradouro || ''}
              onChange={(e) => setSec('endereco', 'logradouro', e.target.value)} /></Campo>
          <div className="linha2">
            <Campo rotulo="Número" dica="nº da casa/lote; se não houver, S/N">
              <input value={en.numero || ''}
                onChange={(e) => setSec('endereco', 'numero', e.target.value)} /></Campo>
            <Campo rotulo="Complemento (opcional)" dica="apto, bloco, casa...">
              <input value={en.complemento || ''}
                onChange={(e) => setSec('endereco', 'complemento', e.target.value)} /></Campo>
          </div>
        </>)}
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
        <LeitorRG token={token} dados={dados} setDados={setDados} salvar={async (novos) => {
          // Persiste as duas seções tocadas pelas sugestões (autosave é por etapa).
          await api.salvarSecao(token, 'documentos', novos.documentos)
          await api.salvarSecao(token, 'pessoais', novos.pessoais)
        }} />
        <Campo rotulo="RG — número" dica="a CNH não substitui o RG">
          <input value={doc.rg_numero || ''}
                 onChange={(e) => setSec('documentos', 'rg_numero', e.target.value)} /></Campo>
        <div className="linha2">
          <Campo rotulo="Órgão emissor" dica="ex.: SSP/DF"><input value={doc.rg_orgao_emissor || ''}
            onChange={(e) => setSec('documentos', 'rg_orgao_emissor', e.target.value)} /></Campo>
          <Campo rotulo="Data de expedição"><InputData valor={doc.rg_data_expedicao || ''}
            onChange={(v) => setSec('documentos', 'rg_data_expedicao', v)} /></Campo>
        </div>
        <Campo rotulo="CPF"><input inputMode="numeric" maxLength={14} value={fmtCpf(doc.cpf)}
          onChange={(e) => setSec('documentos', 'cpf', e.target.value.replace(/\D/g, ''))} />
          <AvisoCpf cpf={doc.cpf} /></Campo>
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
        {doc.cnh_numero && <>
          <div className="linha2">
            <Campo rotulo="CNH — órgão emissor" dica="ex.: DETRAN"><input value={doc.cnh_orgao_emissor || ''}
              onChange={(e) => setSec('documentos', 'cnh_orgao_emissor', e.target.value)} /></Campo>
            <Campo rotulo="CNH — UF"><input maxLength={2} value={doc.cnh_uf || ''}
              onChange={(e) => setSec('documentos', 'cnh_uf', e.target.value.toUpperCase())} /></Campo>
          </div>
          <div className="linha2">
            <Campo rotulo="CNH — data de emissão"><InputData valor={doc.cnh_data_emissao || ''}
              onChange={(v) => setSec('documentos', 'cnh_data_emissao', v)} /></Campo>
            <Campo rotulo="CNH — validade"><InputData valor={doc.cnh_validade || ''}
              onChange={(v) => setSec('documentos', 'cnh_validade', v)} /></Campo>
          </div>
          <Campo rotulo="CNH — 1ª habilitação"><InputData valor={doc.cnh_primeira_habilitacao || ''}
            onChange={(v) => setSec('documentos', 'cnh_primeira_habilitacao', v)} /></Campo>
        </>}
        <Campo rotulo="Situação militar — documento (se tiver)"
               ajuda="Obrigatório para homens de 18 a 45 anos: Certificado de Reservista, de Alistamento Militar (CAM) ou de Dispensa de Incorporação (CDI).">
          <select value={doc.militar_tipo || ''}
                  onChange={(e) => setSec('documentos', 'militar_tipo', e.target.value || null)}>
            <option value="">Não se aplica</option>
            <option value="reservista">Certificado de Reservista</option>
            <option value="alistamento">Certificado de Alistamento Militar (CAM)</option>
            <option value="dispensa">Certificado de Dispensa de Incorporação (CDI)</option>
          </select></Campo>
        {doc.militar_tipo && <>
          <div className="linha2">
            <Campo rotulo="Nº do certificado (RA)"><input value={doc.militar_numero || ''}
              onChange={(e) => setSec('documentos', 'militar_numero', e.target.value)} /></Campo>
            <Campo rotulo="Série"><input value={doc.militar_serie || ''}
              onChange={(e) => setSec('documentos', 'militar_serie', e.target.value)} /></Campo>
          </div>
          <div className="linha2">
            <Campo rotulo="Categoria" dica="ex.: 1ª, 2ª ou 3ª categoria"><input value={doc.militar_categoria || ''}
              onChange={(e) => setSec('documentos', 'militar_categoria', e.target.value)} /></Campo>
            <Campo rotulo="Data de expedição"><InputData valor={doc.militar_data_emissao || ''}
              onChange={(v) => setSec('documentos', 'militar_data_emissao', v)} /></Campo>
          </div>
          <Campo rotulo="Órgão expedidor" dica="ex.: Junta de Serviço Militar / Ministério da Defesa">
            <input value={doc.militar_orgao || ''}
                   onChange={(e) => setSec('documentos', 'militar_orgao', e.target.value)} /></Campo>
        </>}
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
              <Campo rotulo="Nascimento"><InputData valor={dep.data_nascimento || ''}
                onChange={(v) => atualizaDep(i, 'data_nascimento', v)} /></Campo>
              <Campo rotulo="CPF"><input inputMode="numeric" maxLength={14} value={fmtCpf(dep.cpf)}
                onChange={(e) => atualizaDep(i, 'cpf', e.target.value.replace(/\D/g, ''))} />
                <AvisoCpf cpf={dep.cpf} /></Campo>
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
        <BlocoCreche token={token} />
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
          {(en.uf || '').toUpperCase() === 'GO' && (
            <div className="alerta" style={{ borderLeft: '4px solid var(--verde)' }}>
              <strong>🚌 Você mora em Goiás:</strong> para o seu Vale-Transporte, a Green House
              irá solicitar o(s) cartão(ões) de mobilidade da sua região (ex.: UTB) vinculados
              ao CNPJ da empresa. Isso é feito por nós — você não precisa providenciar nada,
              apenas ficar ciente.
              <label style={{ display: 'flex', gap: '.5rem', marginTop: '.6rem', alignItems: 'center' }}>
                <input type="checkbox" checked={Boolean(ve.vt_ciencia_cartao_go)}
                       disabled={Boolean(ve.vt_ciencia_cartao_go)}
                       onChange={(e) => setSec('vt_emergencia', 'vt_ciencia_cartao_go', e.target.checked)} />
                <span>Estou ciente de que a empresa solicitará o(s) cartão(ões) em meu nome.</span>
              </label>
            </div>
          )}
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
                <input placeholder="(61) 99999-8888" inputMode="tel" value={fmtTelefone(c.telefone_celular)}
                       onChange={(e) => atualizaContato(i, 'telefone_celular',
                                                        fmtTelefone(e.target.value))} /></Campo>
            </div>
          </fieldset>
        ))}
        <button className="btn-secundario" onClick={() => setDados((d) => ({
          ...d, contatos: [...d.contatos, { nome_completo: '', parentesco: '', telefone_celular: '' }],
        }))}>+ Adicionar contato</button>
      </>}

      {erroSalvar && <div className="alerta">{erroSalvar}</div>}

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

// Bloco opcional do Reembolso-Creche na admissão: só aparece se o posto do
// candidato dá direito ao benefício (IN SEGES/MGI 147/2026). O candidato já
// entra "certo", informando as crianças até 5 anos e 11 meses.
function BlocoCreche({ token }) {
  const [status, setStatus] = useState(null)
  const [nova, setNova] = useState({ nome: '', data_nascimento: '', parentesco: 'filho' })
  const [erro, setErro] = useState(null)

  const recarregar = () => api.crecheStatus(token).then(setStatus).catch(() => setStatus({ posto_da_direito: false }))
  useEffect(() => { recarregar() }, [])

  if (!status || !status.posto_da_direito) return null

  const add = async () => {
    if (!nova.nome.trim() || !nova.data_nascimento.trim()) { setErro('Informe nome e data de nascimento.'); return }
    setErro(null)
    try { await api.crecheAddCrianca(token, nova); setNova({ nome: '', data_nascimento: '', parentesco: 'filho' }); recarregar() }
    catch { setErro('Não foi possível adicionar. Tente de novo.') }
  }
  const subir = async (id, tipo, arquivo) => {
    if (!arquivo) return
    try { await api.crecheSubirDoc(token, id, tipo, arquivo); recarregar() }
    catch (e) { setErro(`Falha ao enviar o arquivo (${e.detail || e.message}).`) }
  }

  return (
    <div className="rh-card" style={{ marginTop: '1rem', borderColor: 'var(--verde)' }}>
      <h3>🍼 Reembolso-Creche (opcional)</h3>
      <p className="explica">Seu posto de trabalho <strong>{status.posto}</strong> pode dar direito ao
        Reembolso-Creche (IN SEGES/MGI nº 147/2026). Se você tem filho(a), enteado(a) ou criança sob
        guarda judicial com <strong>até 5 anos e 11 meses</strong>, informe aqui para já entrar com o
        pedido — anexando a certidão de nascimento. A análise de elegibilidade é feita pelo RH.</p>

      {(status.criancas || []).map((c) => (
        <div key={c.id} className="creche-crianca">
          <div className="creche-crianca-topo">
            <strong>{c.nome}</strong>
            <span className="explica" style={{ margin: 0 }}>{c.parentesco} · nasc. {c.data_nascimento}</span>
            <button className="btn-link" onClick={() => api.crecheDelCrianca(token, c.id).then(recarregar)}>remover</button>
          </div>
          <div className="creche-docs">
            <label className={`creche-doc ${c.tem_certidao ? 'ok' : ''}`}>
              {c.tem_certidao ? '✅ Certidão enviada' : '📎 Certidão de nascimento'}
              <input type="file" hidden accept="image/*,.pdf"
                     onChange={(e) => subir(c.id, 'certidao', e.target.files?.[0])} />
            </label>
            <label className={`creche-doc ${c.tem_guarda ? 'ok' : ''}`}>
              {c.tem_guarda ? '✅ Guarda enviada' : '📎 Guarda judicial (se aplicável)'}
              <input type="file" hidden accept="image/*,.pdf"
                     onChange={(e) => subir(c.id, 'guarda', e.target.files?.[0])} />
            </label>
          </div>
        </div>
      ))}

      <div className="linha3" style={{ marginTop: '.6rem' }}>
        <label className="campo"><span className="rotulo">Nome da criança</span>
          <input value={nova.nome} onChange={(e) => setNova({ ...nova, nome: e.target.value })} /></label>
        <label className="campo"><span className="rotulo">Data de nascimento</span>
          <input placeholder="dd/mm/aaaa" value={nova.data_nascimento}
                 onChange={(e) => setNova({ ...nova, data_nascimento: e.target.value })} /></label>
        <label className="campo"><span className="rotulo">Vínculo</span>
          <select value={nova.parentesco} onChange={(e) => setNova({ ...nova, parentesco: e.target.value })}>
            <option value="filho">Filho(a)</option>
            <option value="enteado">Enteado(a)</option>
            <option value="guarda">Guarda judicial</option>
          </select></label>
      </div>
      {erro && <div className="alerta">{erro}</div>}
      <button className="btn-secundario" onClick={add}>+ Adicionar criança</button>
    </div>
  )
}
