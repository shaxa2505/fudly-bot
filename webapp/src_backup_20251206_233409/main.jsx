import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { CartProvider } from './context/CartContext'
import ErrorBoundary from './components/ErrorBoundary'
import { initSentry } from './utils/sentry'
import './index.css'

// Initialize Sentry for error tracking (must be early)
initSentry()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <CartProvider>
        <App />
      </CartProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
