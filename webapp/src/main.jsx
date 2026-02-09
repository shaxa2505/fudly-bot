import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { CartProvider } from './context/CartContext'
import ErrorBoundary from './components/ErrorBoundary'
import { initSentry } from './utils/sentry'
import './index.css'

const persistDebugFlag = () => {
  if (typeof window === 'undefined') return
  try {
    const href = String(window.location?.href || '')
    const search = String(window.location?.search || '')
    const hash = String(window.location?.hash || '')
    const searchParams = new URLSearchParams(search.startsWith('?') ? search : '')
    const hashParams = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : '')
    const debugValue =
      searchParams.get('debug') ||
      hashParams.get('debug') ||
      (href.includes('debug=1') ? '1' : '') ||
      (href.includes('debug=true') ? 'true' : '')
    if (debugValue === '1' || debugValue === 'true') {
      window.localStorage?.setItem('fudly_debug', '1')
      window.sessionStorage?.setItem('fudly_debug', '1')
    }
  } catch {
    // ignore debug flag failures
  }
}

// Initialize Sentry for error tracking (must be early)
initSentry()
persistDebugFlag()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <CartProvider>
        <App />
      </CartProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
