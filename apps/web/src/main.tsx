import { canvas, InstUISettingsProvider } from '@instructure/ui'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { shouldRetry } from './api/client'
import App from './App'
import { DemoUserProvider } from './shell/demoUser'
import './shell/shell.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: shouldRetry, staleTime: 30_000 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <InstUISettingsProvider theme={canvas}>
      <QueryClientProvider client={queryClient}>
        <DemoUserProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </DemoUserProvider>
      </QueryClientProvider>
    </InstUISettingsProvider>
  </StrictMode>,
)
