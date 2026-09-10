import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'

import { App } from './App'
import { RealtimeProvider } from './realtime/RealtimeProvider'
import { DemoModeProvider } from './demo/DemoModeProvider'
import './styles/global.css'

const root = document.getElementById('root')

if (root === null) {
  throw new Error('Application root element was not found.')
}

createRoot(root).render(
  <BrowserRouter>
    <DemoModeProvider>
      <RealtimeProvider>
        <App />
      </RealtimeProvider>
    </DemoModeProvider>
  </BrowserRouter>,
)
