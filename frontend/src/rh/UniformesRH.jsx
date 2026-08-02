import { useEffect, useState } from 'react'
import { rh as api } from '../api.js'
import DashPlanilha from './DashPlanilha.jsx'

// Tamanhos de uniforme de quem está em admissão (v2.07, feedback 2026-07-28).
//
// O Bruno pediu "um e-mail para o Gabriel, o Vitor e o operacional com todas as
// informações de uniforme" e, ao ser perguntado, escolheu TELA + e-mail só de
// aviso: nome, posto e medidas numa tabela por e-mail é ficha de pessoal
// circulando em caixa que ninguém controla, e a cada 20 admissões seriam 20
// e-mails que o time para de ler. Quem recebe o empurrão se configura em
// Configurações → Avisos internos (evento "Uniforme").

const ouTraco = (v) => v || '—';

export default function UniformesRH({ aoVoltar, abrirPessoa }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)

  useEffect(() => {
    api.uniformes()
      .then(setDados)
      .catch(() => setErro('Não foi possível carregar a lista de uniformes.'))
  }, [])

  const colunas = [
    { chave: 'nome', rotulo: 'Nome', sempreVisivel: true, ordenavel: true, filtro: 'texto',
      valor: (l) => l.nome,
      render: (l) => (abrirPessoa
        ? <button className="btn-link" onClick={() => abrirPessoa(l.candidato_id)}>{l.nome}</button>
        : l.nome) },
    { chave: 'cargo', rotulo: 'Cargo', ordenavel: true, filtro: 'lista', quebra: true,
      valor: (l) => ouTraco(l.cargo) },
    { chave: 'posto', rotulo: 'Posto', ordenavel: true, filtro: 'lista', quebra: true,
      valor: (l) => ouTraco(l.posto) },
    { chave: 'camisa', rotulo: 'Camisa', ordenavel: true, filtro: 'lista',
      valor: (l) => ouTraco(l.camisa) },
    { chave: 'calca', rotulo: 'Calça', ordenavel: true, filtro: 'lista',
      valor: (l) => ouTraco(l.calca) },
    { chave: 'calcado', rotulo: 'Calçado', ordenavel: true, filtro: 'lista',
      valor: (l) => ouTraco(l.calcado) },
    { chave: 'completo', rotulo: 'Situação', ordenavel: true, filtro: 'select',
      opcoes: ['Completo', 'Falta informar'],
      valor: (l) => (l.completo ? 'Completo' : 'Falta informar') },
  ]

  const cards = dados ? [
    { rotulo: 'Em admissão', valor: dados.total },
    { rotulo: 'Falta informar', valor: dados.faltando, cor: '#e9a63a',
      filtro: { chave: 'completo', valor: 'Falta informar' } },
  ] : null

  return (
    <main className="rh-painel">
      <header className="rh-topo">
        {aoVoltar && <button className="btn-link" onClick={aoVoltar}>← Voltar</button>}
        <h1>👕 Uniformes</h1>
        <div />
      </header>
      <p className="explica">Tamanhos informados por quem está <strong>em admissão</strong>.
        Use o botão de exportar para mandar a lista a quem compra. Para avisar o
        operacional automaticamente a cada novo admitido, configure o evento
        <strong> Uniforme</strong> em Configurações → Avisos internos.</p>

      {erro && <div className="alerta">{erro}</div>}
      {!dados ? <p>Carregando…</p> : (
        <DashPlanilha id="uniformes" colunas={colunas} dados={dados.linhas} cards={cards}
                      vazio="Ninguém em admissão no momento." />
      )}
    </main>
  )
}
