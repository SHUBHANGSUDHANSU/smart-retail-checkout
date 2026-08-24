import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'

import { App } from './App'
import './styles/global.css'

const root = document.getElementById('root')

if (root === null) {
  throw new Error('Application root element was not found.')
}

createRoot(root).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>,
)
