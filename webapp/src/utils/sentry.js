/**
 * Sentry Integration for Error Tracking
 *
 * Initialize early in the app to catch all errors.
 * DSN should be set in environment variable VITE_SENTRY_DSN
 */
import * as Sentry from '@sentry/react'

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN || ''
const ENVIRONMENT = import.meta.env.MODE || 'development'

/**
 * Initialize Sentry error tracking
 */
export function initSentry() {
  if (!SENTRY_DSN) {
    console.log('Sentry DSN not configured, skipping initialization')
    return false
  }

  try {
    Sentry.init({
      dsn: SENTRY_DSN,
      environment: ENVIRONMENT,
      integrations: [
        Sentry.browserTracingIntegration(),
        Sentry.replayIntegration({
          // Capture 10% of sessions for replay
          maskAllText: true,
          blockAllMedia: true,
        }),
      ],
      // Performance monitoring
      tracesSampleRate: 0.1, // 10% of transactions
      // Session replay
      replaysSessionSampleRate: 0.1, // 10% of sessions
      replaysOnErrorSampleRate: 1.0, // 100% of sessions with errors

      // Filter out noisy errors
      ignoreErrors: [
        'ResizeObserver loop',
        'Network request failed',
        'Load failed',
        'ChunkLoadError',
      ],

      // Add Telegram user context
      beforeSend(event) {
        const tg = window.Telegram?.WebApp
        if (tg?.initDataUnsafe?.user) {
          event.user = {
            id: String(tg.initDataUnsafe.user.id),
            username: tg.initDataUnsafe.user.username,
          }
        }
        return event
      },
    })

    console.log(`Sentry initialized for environment: ${ENVIRONMENT}`)
    return true
  } catch (error) {
    console.warn('Failed to initialize Sentry:', error)
    return false
  }
}

/**
 * Set user context for Sentry events
 */
export function setUser(userId, username = null) {
  try {
    Sentry.setUser({
      id: String(userId),
      username: username,
    })
  } catch (e) {
    // Ignore
  }
}

/**
 * Capture an exception manually
 */
export function captureException(error, context = {}) {
  try {
    Sentry.withScope((scope) => {
      Object.entries(context).forEach(([key, value]) => {
        scope.setExtra(key, value)
      })
      Sentry.captureException(error)
    })
  } catch (e) {
    console.error('Failed to capture exception:', error)
  }
}

/**
 * Capture a message
 */
export function captureMessage(message, level = 'info', context = {}) {
  try {
    Sentry.withScope((scope) => {
      Object.entries(context).forEach(([key, value]) => {
        scope.setExtra(key, value)
      })
      Sentry.captureMessage(message, level)
    })
  } catch (e) {
    // Ignore
  }
}

/**
 * Error Boundary component powered by Sentry
 */
export const SentryErrorBoundary = Sentry.ErrorBoundary

export default {
  initSentry,
  setUser,
  captureException,
  captureMessage,
  SentryErrorBoundary,
}
