import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import SelectBusca from '../SelectBusca.jsx'

/**
 * Cadastro de talento À MÃO, pelo painel (v2.73).
 *
 * Por que existe: **não havia porta para o RH cadastrar uma pessoa** — só o
 * formulário público (`/banco-de-talentos`) e a importação de planilha do Forms.
 * O currículo que chega por e-mail ou por indicação ficava de fora do Banco de
 * Talentos, ou obrigava a pedir que a pessoa preenchesse o formulário de novo.
 *
 * Duas decisões que a tela precisa deixar VISÍVEIS:
 *
 * 1. **Consentimento.** A pessoa não está aqui para marcar "li e concordo",
 *    então o carimbo fica em branco e a ficha dirá "cadastrado pelo RH — sem
 *    consentimento registrado". A tela diz isso ANTES de cadastrar, não depois:
 *    quem cadastra precisa saber o que está (e o que não está) sendo registrado.
 * 2. **Duplicata avisa, não funde.** O 409 do servidor traz QUEM já existe, e a
 *    tela mostra o nome com a opção de cadastrar assim mesmo (homônimo real
 *    existe). É a regra da casa para equivalência assistida — o sistema propõe,
 *    o humano decide.
 *
 * Composição copiada do formulário de nova entrevista (`EntrevistasRH.jsx`):
 * `.rh-card` + `.rh-topo` + `.rh-grid-2`, `<span className="rotulo">` dentro de
 * `.campo`, `SelectBusca` em vez de `<select>` nativo. A regra da v2.65 é abrir
 * a tela equivalente que já existe e copiar a COMPOSIÇÃO dela.
 */
export default function NovoTalento({ aoFechar, aoCriar, aoAbrirExistente }) {
  const [f, setF] = useState({
    nome: '', email: '', telefone: '', cidade: '', escolaridade: '',
    origem: 'Currículo por e-mail', tipo_contratacao: '', resumo: '',
  })
  const [cargos, setCargos] = useState([])
  const [regioes, setRegioes] = useState([])
  const [opcoes, setOpcoes] = useState({ cargos: [], regioes: [] })
  const [erro, setErro] = useState(null)
  const [duplicata, setDuplicata] = useState(null)
  const [salvando, setSalvando] = useState(false)

  // As mesmas listas do formulário público (rota pública, sem token): cargo
  // digitado à mão vira "Vigia"/"vigia"/"Vigía" — três cargos onde há um só.
  useEffect(() => { api.opcoesTalento().then(setOpcoes).catch(() => {}) }, [])

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  // Marcar/desmarcar item de lista múltipla (cargos, regiões).
  const alterna = (lista, setLista) => (v) =>
    setLista(lista.includes(v) ? lista.filter((x) => x !== v) : [...lista, v])

  const salvar = async (forcar = false) => {
    setErro(null)
    if (!f.nome.trim()) { setErro('O nome é obrigatório.'); return }
    setSalvando(true)
    try {
      const criado = await api.cadastrarTalento({
        ...f, cargos_interesse: cargos, regioes, forcar,
      })
      aoCriar(criado)
    } catch (e) {
      // O 409 traz quem já existe em `e.dados` (o `api.js` preserva o `detail`
      // estruturado desde a v2.55) — sem isso a tela só saberia dizer "não deu".
      if (e.status === 409 && e.dados?.erro === 'talento_ja_existe') {
        setDuplicata(e.dados)
      } else {
        setErro(`Não foi possível cadastrar (${e.detail || e.message}).`)
      }
    } finally { setSalvando(false) }
  }

  return (
    <div className="rh-card">
      <div className="rh-topo">
        <h3>Cadastrar talento</h3>
        <button className="btn-secundario btn-mini" onClick={aoFechar}>✕ fechar</button>
      </div>

      {/* O aviso vem ANTES do formulário, não depois de salvar: quem cadastra
          precisa saber o que fica registrado — e o que NÃO fica. */}
      <p className="explica">
        A pessoa não está aqui para aceitar os termos, então o cadastro fica
        <strong> sem consentimento LGPD registrado</strong> e guarda o seu nome
        como responsável. Para ter o aceite dela, mande o link do
        Banco de Talentos em vez de cadastrar aqui.
      </p>

      {duplicata && (
        <div className="aviso-inline">
          <strong>Já existe alguém assim:</strong> {duplicata.nome}
          {duplicata.email ? ` (${duplicata.email})` : ''} — casou por{' '}
          {duplicata.por === 'email' ? 'e-mail' : 'nome e telefone'}.
          <div className="navegacao">
            <button className="btn-secundario btn-mini"
                    onClick={() => aoAbrirExistente(duplicata.id)}>
              Ver quem já está cadastrado
            </button>
            {/* Homônimo real existe numa base de 1.171 pessoas — o caminho
                existe, mas é o secundário, e fica na auditoria. */}
            <button className="btn-link" disabled={salvando}
                    onClick={() => { setDuplicata(null); salvar(true) }}>
              É outra pessoa, cadastrar assim mesmo
            </button>
          </div>
        </div>
      )}

      <div className="rh-grid-2">
        <label className="campo">
          <span className="rotulo">Nome completo</span>
          <input value={f.nome} onChange={set('nome')} autoComplete="off"
                 placeholder="Como está no documento" />
        </label>
        <label className="campo">
          <span className="rotulo">E-mail
            <span className="dica-inline"> — opcional; é por ele que o teste é enviado</span></span>
          <input type="email" value={f.email} onChange={set('email')} autoComplete="off" />
        </label>
        <label className="campo">
          <span className="rotulo">Telefone</span>
          <input value={f.telefone} onChange={set('telefone')} autoComplete="off" />
        </label>
        <label className="campo">
          <span className="rotulo">Cidade</span>
          <input value={f.cidade} onChange={set('cidade')} autoComplete="off" />
        </label>
        <div className="campo">
          <span className="rotulo">De onde veio
            <span className="dica-inline"> — para saber por onde a pessoa chegou</span></span>
          <SelectBusca valor={f.origem} aoEscolher={(v) => setF({ ...f, origem: v })}>
            <option value="Currículo por e-mail">Currículo por e-mail</option>
            <option value="Indicação">Indicação</option>
            <option value="Currículo em papel">Currículo em papel</option>
            <option value="Procurou presencialmente">Procurou presencialmente</option>
            <option value="Telefone">Telefone</option>
            <option value="Outro">Outro</option>
          </SelectBusca>
        </div>
        <div className="campo">
          <span className="rotulo">Tipo de contratação</span>
          <SelectBusca valor={f.tipo_contratacao}
                       aoEscolher={(v) => setF({ ...f, tipo_contratacao: v })}>
            <option value="">— não informado —</option>
            <option value="efetivo">Efetivo</option>
            <option value="intermitente">Intermitente</option>
            <option value="tanto_faz">Tanto faz</option>
          </SelectBusca>
        </div>
        <label className="campo">
          <span className="rotulo">Escolaridade</span>
          <input value={f.escolaridade} onChange={set('escolaridade')} autoComplete="off" />
        </label>
      </div>

      {/* Cargos e regiões são MÚLTIPLA ESCOLHA — `.chips-escolha` é a primitiva
          específica disso (v2.65): uma lista suspensa obrigaria a abrir e
          escolher item a item para algo que se lê de uma vez. */}
      <div className="campo">
        <span className="rotulo">Cargos de interesse</span>
        <div className="chips-escolha">
          {opcoes.cargos.map((c) => (
            <button key={c} type="button"
                    className={`chip-escolha${cargos.includes(c) ? ' on' : ''}`}
                    onClick={() => alterna(cargos, setCargos)(c)}>{c}</button>
          ))}
        </div>
      </div>
      <div className="campo">
        <span className="rotulo">Regiões onde pode trabalhar</span>
        <div className="chips-escolha">
          {opcoes.regioes.map((r) => (
            <button key={r} type="button"
                    className={`chip-escolha${regioes.includes(r) ? ' on' : ''}`}
                    onClick={() => alterna(regioes, setRegioes)(r)}>{r}</button>
          ))}
        </div>
      </div>

      <label className="campo">
        <span className="rotulo">Experiência / observações
          <span className="dica-inline"> — o que a pessoa contou, ou o que o currículo diz</span></span>
        <textarea rows={4} value={f.resumo} onChange={set('resumo')} />
      </label>

      {erro && <p className="alerta">{erro}</p>}

      <div className="navegacao">
        <button className="btn-principal" disabled={salvando} onClick={() => salvar(false)}>
          {salvando ? 'Cadastrando…' : 'Cadastrar'}
        </button>
        <button className="btn-secundario" onClick={aoFechar}>Cancelar</button>
      </div>
      <p className="explica">
        O currículo pode ser anexado depois, pela ficha da pessoa.
      </p>
    </div>
  )
}
