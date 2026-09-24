import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.jsx'
import { queryClient } from './queryClient.js'
import CrashFallback from './components/CrashFallback.jsx'
import { ErrorBoundary, initSentry } from './observability.js'

// No-op unless VITE_SENTRY_DSN is set. Called before render so a crash during
// the first paint is still reported.
initSentry()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary fallback={CrashFallback}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
