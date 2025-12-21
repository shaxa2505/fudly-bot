import { useEffect } from 'react'
import './ErrorFallback.css'

/**
 * Error Fallback UI component
 * Shown when error boundary catches an error
 */
function ErrorFallback({ error, resetErrorBoundary }) {
  useEffect(() => {
    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
  }, [])

  const isDevelopment = import.meta.env.MODE === 'development'

  return (
    <div className="error-fallback">
      <div className="error-fallback-content">
        <div className="error-fallback-icon">!</div>

        <h2 className="error-fallback-title">
          Xatolik yuz berdi
        </h2>

        <p className="error-fallback-message">
          Nimadir noto'g'ri ketdi. Iltimos, qayta urinib ko'ring.
        </p>

        {isDevelopment && error && (
          <details className="error-fallback-details">
            <summary>Texnik ma'lumot (faqat dev)</summary>
            <pre className="error-fallback-stack">
              {error.message}
              {'\n\n'}
              {error.stack}
            </pre>
          </details>
        )}

        <div className="error-fallback-actions">
          <button
            className="error-fallback-btn primary"
            onClick={resetErrorBoundary}
          >
            Qayta yuklash
          </button>

          <button
            className="error-fallback-btn secondary"
            onClick={() => {
              if (window.Telegram?.WebApp) {
                window.Telegram.WebApp.close()
              } else {
                window.location.href = '/'
              }
            }}
          >
            Bosh sahifa
          </button>
        </div>

        <div className="error-fallback-help">
          <p>Muammo takrorlanayotganmi?</p>
          <a
            href="https://t.me/fudly_support"
            className="error-fallback-link"
            target="_blank"
            rel="noopener noreferrer"
          >
            Qo'llab-quvvatlash
          </a>
        </div>
      </div>
    </div>
  )
}

/**
 * Simpler inline error display (for non-critical errors)
 */
export function InlineError({ error, onRetry, onDismiss }) {
  if (!error) return null

  return (
    <div className="inline-error">
      <div className="inline-error-content">
        <span className="inline-error-icon">!</span>
        <p className="inline-error-message">{error}</p>
      </div>

      <div className="inline-error-actions">
        {onRetry && (
          <button
            className="inline-error-btn retry"
            onClick={onRetry}
          >
            Qayta
          </button>
        )}
        {onDismiss && (
          <button
            className="inline-error-btn dismiss"
            onClick={onDismiss}
          >
            x
          </button>
        )}
      </div>
    </div>
  )
}

export default ErrorFallback
