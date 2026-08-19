import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import SelectBusca from '../SelectBusca.jsx'
import { fmtDataHora } from '../fmt.js'

// Credenciais de MÁQUINA (v2.94). As rotas existiam desde então e NÃO havia
// tela: criar um token exigia `docker exec` no container, o que na prática
// significava que o recurso não existia para quem opera.
//
// Três coisas que esta tela precisa fazer certo, porque o desenho da credencial
// depende delas (ver `services/token_automacao.py`):
//
// 1. AVISAR ANTES de emitir que o segredo aparece uma única vez. Quem descobre
//    depois guarda o segredo "por garantia" em outro lugar — exatamente o que o
//    desenho evita ao gravar só o sha256.
// 2. Mostrar PREFIXO e ÚLTIMO USO, que é o que responde "qual eu revogo?" e
//    "este ainda está em uso?" sem revelar segredo nenhum.
// 3. Deixar claro que revogar MARCA e não apaga: a linha é prova de que a
//    credencial existiu e de quando deixou de valer.
export default function TokensAutomacao() {
  const [tokens, setTokens] = useState(null)
  const [usuarios, setUsuarios] = useState([])
  const [erro, setErro] = useState(null)
  const [criando, setCriando] = useState(false)
  const [novo, setNovo] = useState({ usuario_id: '', descricao: '', dias_validade: '' })
  const [segredo, setSegredo] = useState(null)   // aparece UMA vez
  const [copiado, setCopiado] = useState(false)

  const recarregar = () => api.tokensAutomacao().then(setTokens)
  useEffect(() => {
    recarregar().catch((e) => setErro(e.detail || e.message))
    api.usuarios().then(setUsuarios).catch(() => setUsuarios([]))
  }, [])

  const criar = async () => {
    if (!novo.usuario_id) { setErro('Escolha o usuário dono da credencial.'); return }
    if (!novo.descricao.trim()) { setErro('Descreva para que serve — sem isso, revogar vira adivinhação.'); return }
    setErro(null)
    try {
      const r = await api.criarTokenAutomacao({
        usuario_id: novo.usuario_id,
        descricao: novo.descricao.trim(),
        dias_validade: novo.dias_validade ? parseInt(novo.dias_validade, 10) : null,
      })
      setSegredo(r.token)
      setCriando(false)
      setNovo({ usuario_id: '', descricao: '', dias_validade: '' })
      await recarregar()
    } catch (e) {
      setErro(e.detail === 'usuario_inativo'
        ? 'Este usuário está inativo — reative-o antes, ou escolha outro.'
        : e.detail === 'descricao_obrigatoria' ? 'Descreva para que serve a credencial.'
        : `Não foi possível criar (${e.detail || e.message}).`)
    }
  }

  const revogar = async (t) => {
    if (!window.confirm(`Revogar "${t.descricao}" (${t.prefixo})?\n\n`
      + 'O acesso é cortado na hora. O registro PERMANECE na lista, marcado como '
      + 'revogado — é a prova de que a credencial existiu e de quando deixou de valer.')) return
    try { await api.revogarTokenAutomacao(t.id); await recarregar() }
    catch (e) { setErro(`Não foi possível revogar (${e.detail || e.message}).`) }
  }

  const copiar = async () => {
    try { await navigator.clipboard.writeText(segredo); setCopiado(true) }
    catch { setCopiado(false) }
  }

  // Só usuários ATIVOS podem receber credencial (a rota recusa inativo com 422);
  // oferecer os inativos na lista seria convidar ao erro.
  const ativos = usuarios.filter((u) => u.ativo)

  return (
    <div className="rh-card">
      <h3>🤖 Credenciais de automação</h3>
      <p className="explica">Para programas que consultam o portal (integrações, scripts),
        no lugar da senha de uma pessoa. A credencial é <strong>revogável a qualquer
        momento</strong> e vale o que o <strong>papel do usuário</strong> dono dela permite —
        para diagnóstico, use um usuário com o papel <strong>automação</strong>, que tem
        4 permissões contra as 27 do RH.</p>

      {erro && <div className="alerta">{erro}</div>}

      {/* O segredo aparece UMA vez. Fica em bloco destacado, com o aviso ANTES
          do valor — não adianta avisar embaixo de algo que já foi lido. */}
      {segredo && (
        <div className="rh-card" style={{ borderColor: 'var(--verde)' }}>
          <strong>Copie agora — este segredo não aparece de novo.</strong>
          <p className="explica" style={{ margin: '.3rem 0' }}>O sistema guarda apenas um
            resumo criptográfico dele. Se perder, revogue esta credencial e emita outra —
            é o comportamento certo, não um incômodo a contornar guardando o segredo
            em outro lugar.</p>
          <div className="bloco-codigo" style={{ wordBreak: 'break-all' }}>{segredo}</div>
          <div className="rh-lote" style={{ marginTop: '.4rem' }}>
            <button className="btn-secundario btn-mini" onClick={copiar}>
              {copiado ? '✓ Copiado' : '📋 Copiar'}</button>
            <button className="btn-link" onClick={() => { setSegredo(null); setCopiado(false) }}>
              Já copiei, fechar</button>
          </div>
        </div>
      )}

      {criando ? (
        <div className="rh-card">
          <h4 style={{ margin: '0 0 .3rem' }}>Nova credencial</h4>
          <p className="explica" style={{ margin: '0 0 .5rem' }}>⚠️ O segredo será mostrado
            <strong> uma única vez</strong>, logo após criar. Tenha onde guardá-lo antes de
            continuar.</p>
          <div className="linha3">
            <label className="campo"><span className="rotulo">Usuário dono</span>
              <SelectBusca valor={novo.usuario_id} placeholder="Buscar usuário…"
                           vazioRotulo="— escolha —"
                           aoEscolher={(v) => setNovo({ ...novo, usuario_id: v })}
                           opcoes={ativos.map((u) => ({
                             valor: u.id, rotulo: u.nome || u.email, extra: u.papel }))} />
            </label>
            <label className="campo"><span className="rotulo">Para que serve</span>
              <input value={novo.descricao} placeholder="ex.: integração de diagnóstico"
                     onChange={(e) => setNovo({ ...novo, descricao: e.target.value })} />
            </label>
            <label className="campo"><span className="rotulo">Validade (dias)</span>
              <input type="number" min="1" value={novo.dias_validade} placeholder="em branco = não expira"
                     onChange={(e) => setNovo({ ...novo, dias_validade: e.target.value })} />
            </label>
          </div>
          <div className="rh-lote" style={{ marginTop: '.5rem' }}>
            <button className="btn-principal btn-mini" onClick={criar}>Criar credencial</button>
            <button className="btn-secundario btn-mini"
                    onClick={() => { setCriando(false); setErro(null) }}>Cancelar</button>
          </div>
        </div>
      ) : (
        <button className="btn-secundario btn-mini"
                onClick={() => setCriando(true)}>＋ Nova credencial</button>
      )}

      {tokens === null ? <p>Carregando…</p> : tokens.length === 0 ? (
        <p className="explica">Nenhuma credencial emitida.</p>
      ) : (
        <div className="dash-scroll" style={{ marginTop: '.6rem' }}>
          <table className="rh-tabela">
            <thead><tr>
              <th>Descrição</th><th>Prefixo</th><th>Criada</th>
              <th>Último uso</th><th>Situação</th><th />
            </tr></thead>
            <tbody>
              {tokens.map((t) => (
                <tr key={t.id}>
                  <td>{t.descricao}</td>
                  <td><code>{t.prefixo}</code></td>
                  <td>{fmtDataHora(t.criado_em)}<br />
                    <small className="explica">por {t.criado_por || '—'}</small></td>
                  {/* "Nunca usada" é informação, não defeito: distingue a
                      credencial que ninguém ligou da que está em uso. */}
                  <td>{t.usado_em ? fmtDataHora(t.usado_em)
                    : <span className="explica">nunca usada</span>}</td>
                  <td>{t.valido
                    ? <span className="chip" style={{ '--chip-cor': 'var(--verde-vivo)' }}>válida</span>
                    : <span className="chip" style={{ '--chip-cor': '#999' }}>
                        {t.revogado_em ? 'revogada' : 'expirada'}</span>}
                    {t.expira_em && t.valido && (
                      <><br /><small className="explica">expira {fmtDataHora(t.expira_em)}</small></>)}
                  </td>
                  <td className="acoes-candidato">
                    {t.valido && (
                      <button className="btn-secundario btn-mini"
                              onClick={() => revogar(t)}>Revogar</button>)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
