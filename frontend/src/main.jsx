import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import '@fontsource/outfit/400.css'
import '@fontsource/outfit/600.css'
import '@fontsource/outfit/700.css'
import '@fontsource/outfit/800.css'
import './styles.css'

// Aplica o tema antes do primeiro render (sem "piscada"): escolha salva ou o
// modo do aparelho.
document.documentElement.dataset.tema =
  localStorage.getItem('tema')
  || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro')

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
