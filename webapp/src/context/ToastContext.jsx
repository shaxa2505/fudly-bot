import { createContext, useContext, useState, useCallback, memo } from 'react'
import Toast from '../components/Toast'

/**
 * Toast Context - Global toast notification system
 *
 * Usage:
 * const { showToast } = useToast()
 * showToast({ message: 'Success!', type: 'success' })
 */

const ToastContext = createContext(null)

// Hook to use toast
export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return context
}

// Toast item component
const ToastItem = memo(function ToastItem({ toast, onClose }) {
  return (
    <Toast
      message={toast.message}
      type={toast.type}
      isVisible={true}
      onClose={() => onClose(toast.id)}
      duration={toast.duration}
    />
  )
})

// Multiple toasts container
const ToastContainer = memo(function ToastContainer({ toasts, onClose }) {
  if (toasts.length === 0) return null

  // Only show the most recent toast
  const currentToast = toasts[toasts.length - 1]

  return (
    <ToastItem
      key={currentToast.id}
      toast={currentToast}
      onClose={onClose}
    />
  )
})

// Provider component
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const showToast = useCallback(({
    message,
    type = 'info',
    duration = 3000
  }) => {
    const id = Date.now() + Math.random()

    // Haptic feedback based on type
    if (window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred) {
      if (type === 'success') {
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      } else if (type === 'error') {
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
      } else if (type === 'warning') {
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning')
      }
    }

    setToasts(prev => [...prev, { id, message, type, duration }])

    // Auto-remove after duration
    if (duration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, duration + 300) // Extra time for exit animation
    }

    return id
  }, [])

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  // Convenience methods
  const toast = {
    success: (message, duration) => showToast({ message, type: 'success', duration }),
    error: (message, duration) => showToast({ message, type: 'error', duration }),
    warning: (message, duration) => showToast({ message, type: 'warning', duration }),
    info: (message, duration) => showToast({ message, type: 'info', duration }),
  }

  return (
    <ToastContext.Provider value={{ showToast, removeToast, toast }}>
      {children}
      <ToastContainer toasts={toasts} onClose={removeToast} />
    </ToastContext.Provider>
  )
}

export default ToastContext
