import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import Aviso from '../Aviso.jsx'
import SelectBusca from '../SelectBusca.jsx'

// Papéis e permissões (v2.86) — Configurações → Papéis.
//
// A tela existe para o superadmin ter autonomia sem pedir deploy: criar papel,
// marcar o que cada um pode e ver quantas pessoas já usam. Sem ela, o modelo
// de permissões só seria configurável escrevendo no banco — que é o defeito
// que a v2.68 documentou (chave que nasce lida pelo código e sem tela).
//
// Duas decisões de interface que não são cosméticas:
//
// 1. Permissão PERIGOSA aparece marcada como tal, e o resumo conta quantas
//    são. "Desligar colaborador" e "Ver postos" não podem ter o mesmo peso
//    visual numa lista de 40 caixas — quem marca em massa não lê cada linha.
// 2. O papel do superadmin é exibido, e explicitamente NÃO editável. Esconder
//    o papel faria parecer que ele não existe; deixar editável permitiria
//    fechar a porta por dentro.

export default function PapeisAcesso() {
  const [papeis, setPapeis] = useState(null)
  const [grupos, setGrupos] = useState(null)
  const [erro, setErro] = useState(null)
  const [editando, setEditando] = useState(null)   // {id?, chave, rotulo, descricao, permissoes:Set}
  const [salvando, setSalvando] = useState(false)
  const [aviso, setAviso] = useState(null)

  const recarregar = () => api.papeisAcesso().then(setPapeis)

  useEffect(() => {
    // Estado de erro SEPARADO do "ainda carregando" (regra da v2.46): sem
    // isso, falha de rede deixa a tela em "Carregando…" para sempre, que é
    // indistinguível de internet lenta e não oferece como tentar de novo.
    Promise.all([api.papeisAcesso(), api.catalogoPermissoes()])
      .then(([ps, cat]) => { setPapeis(ps); setGrupos(cat.grupos) })
      .catch(() => setErro('Não foi possível carregar os papéis.'))
  }, [])

  if (erro) {
    return (
      <div className="rh-card">
        <p className="alerta">{erro}</p>
        <button className="btn-secundario" onClick={() => window.location.reload()}>
          Tentar de novo</button>
      </div>
    )
  }
  if (!papeis || !grupos) return <p className="explica">Carregando papéis…</p>

  const todas = grupos.flatMap((g) => g.permissoes)
  const perigosas = (chaves) =>
    todas.filter((p) => p.perigosa && chaves.has(p.chave)).length

  const abrir = (p) => setEditando(p
    ? { ...p, permissoes: new Set(p.permissoes) }
    : { chave: '', rotulo: '', descricao: '', permissoes: new Set() })

  const alternar = (chave) => {
    const conj = new Set(editando.permissoes)
    conj.has(chave) ? conj.delete(chave) : conj.add(chave)
    setEditando({ ...editando, permissoes: conj })
  }

  const salvar = async () => {
    setSalvando(true)
    try {
      const corpo = {
        rotulo: editando.rotulo.trim(),
        descricao: (editando.descricao || '').trim(),
        permissoes: [...editando.permissoes],
      }
      if (editando.id) await api.editarPapelAcesso(editando.id, corpo)
      else await api.criarPapelAcesso({ ...corpo, chave: editando.chave.trim().toLowerCase() })
      setEditando(null)
      await recarregar()
      setAviso({ tipo: 'ok', texto: 'Papel salvo. Vale no próximo acesso de quem o usa.' })
    } catch (e) {
      setAviso({ tipo: 'erro', texto: e.amigavel || e.detail?.mensagem || 'Não foi possível salvar.' })
    } finally { setSalvando(false) }
  }

  const excluir = async (p) => {
    try {
      await api.excluirPapelAcesso(p.id)
      await recarregar()
      setAviso({ tipo: 'ok', texto: `Papel "${p.rotulo}" excluído.` })
    } catch (e) {
      // O 409 do backend diz QUANTAS pessoas usam o papel — repetir isso aqui
      // é o que permite ao superadmin agir (mover as pessoas) em vez de só
      // saber que não deu.
      const d = e.dados || e.detail || {}
      setAviso({
        tipo: 'erro',
        texto: d.usuarios
          ? `${d.usuarios} pessoa(s) usam este papel (${(d.nomes || []).join(', ')}). `
            + 'Mude o papel delas antes de excluir.'
          : (e.amigavel || 'Não foi possível excluir.'),
      })
    }
  }

  return (
    <div className="rh-card">
      {aviso && <Aviso tipo={aviso.tipo} texto={aviso.texto} aoFechar={() => setAviso(null)} />}
      <div className="rh-topo">
        <div>
          <h3>Papéis e permissões</h3>
          <p className="explica">
            O que cada tipo de usuário pode fazer. Módulo novo já nasce liberado
            para o superadministrador e desmarcado para os demais — assim
            ninguém ganha acesso sem alguém conceder.
          </p>
        </div>
        <button className="btn-principal" onClick={() => abrir(null)}>＋ Novo papel</button>
      </div>

      <div className="dash-scroll">
        <table className="rh-tabela">
          <thead>
            <tr><th>Papel</th><th>O que faz</th><th>Permissões</th><th>Pessoas</th><th></th></tr>
          </thead>
          <tbody>
            {papeis.map((p) => (
              <tr key={p.id}>
                <td><strong>{p.rotulo}</strong>{p.de_fabrica && <> <span className="chip">padrão</span></>}</td>
                <td className="dash-quebra">{p.descricao || '—'}</td>
                <td>
                  {p.tudo ? 'Tudo'
                    : <>{p.permissoes.length}
                      {perigosas(new Set(p.permissoes)) > 0 && (
                        <> · <span title="Ações que não se desfazem sozinhas">
                          {perigosas(new Set(p.permissoes))} sensíveis</span></>
                      )}</>}
                </td>
                <td>{p.usuarios}</td>
                <td className="acoes-candidato">
                  {p.tudo ? (
                    <span className="explica" title="Faz tudo por definição — e é o que garante existir quem possa desfazer qualquer engano">
                      não editável</span>
                  ) : (
                    <>
                      <button className="btn-secundario btn-mini" onClick={() => abrir(p)}>Editar</button>
                      {!p.de_fabrica && (
                        <button className="btn-remover btn-mini" onClick={() => excluir(p)}>Excluir</button>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editando && (
        <div className="rh-conferencia">
          <h4 className="rh-conferencia-bloco-titulo">
            {editando.id ? `Editando: ${editando.rotulo}` : 'Novo papel'}
          </h4>
          <div className="rh-grid-2">
            {!editando.id && (
              <label className="campo"><span className="rotulo">Identificador</span>
                <input value={editando.chave} placeholder="ex.: financeiro"
                       onChange={(e) => setEditando({ ...editando, chave: e.target.value })} />
                <small className="explica">Sem espaços. Não muda depois de criado.</small>
              </label>
            )}
            <label className="campo"><span className="rotulo">Nome exibido</span>
              <input value={editando.rotulo}
                     onChange={(e) => setEditando({ ...editando, rotulo: e.target.value })} />
            </label>
            <label className="campo"><span className="rotulo">O que faz</span>
              <input value={editando.descricao || ''}
                     onChange={(e) => setEditando({ ...editando, descricao: e.target.value })} />
            </label>
          </div>

          {grupos.map((g) => (
            <div key={g.grupo} className="rh-conferencia-campos">
              <h5 className="rh-conferencia-bloco-titulo">{g.grupo}</h5>
              {/* Duas/três colunas: 40 permissões numa coluna só viram rolagem
                  sem fim, e ninguém revisa o que não vê de uma vez. */}
              <div className="rh-grid-2">
                {g.permissoes.map((p) => (
                  <label key={p.chave} className="campo-check" title={p.descricao}>
                    <input type="checkbox" checked={editando.permissoes.has(p.chave)}
                           onChange={() => alternar(p.chave)} />
                    <span>
                      {p.rotulo}
                      {p.perigosa && <> <span className="chip" style={{ '--chip-cor': 'var(--ambar)' }}
                                            title="Não se desfaz sozinha">sensível</span></>}
                      <br /><small className="explica">{p.descricao}</small>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          ))}

          <div className="navegacao">
            <button className="btn-principal" disabled={salvando} onClick={salvar}>
              {salvando ? 'Salvando…' : 'Salvar papel'}</button>
            <button className="btn-secundario" onClick={() => setEditando(null)}>Cancelar</button>
            <span className="explica">
              {editando.permissoes.size} permissão(ões)
              {perigosas(editando.permissoes) > 0
                && ` · ${perigosas(editando.permissoes)} sensível(is)`}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

// Seletor de papel reusado na tela de Equipe — para não duplicar a lista de
// papéis em dois lugares que passariam a divergir na primeira mudança.
export function SelectPapel({ valor, aoEscolher, desabilitado }) {
  const [papeis, setPapeis] = useState([])
  useEffect(() => { api.papeisAcesso().then(setPapeis).catch(() => setPapeis([])) }, [])
  return (
    // `aoEscolher` (não `aoMudar`): prop inventada em componente compartilhado
    // não faz nada e não avisa — o React ignora prop desconhecida em silêncio,
    // e o seletor ficaria mudo com o JSX parecendo certo (lição da v2.64).
    <SelectBusca valor={valor} aoEscolher={aoEscolher} desabilitado={desabilitado}
                 opcoes={papeis.map((p) => ({
                   valor: p.chave, rotulo: p.rotulo,
                   extra: p.tudo ? 'faz tudo' : `${p.permissoes.length} permissões`,
                 }))} />
  )
}
